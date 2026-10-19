from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
import os
import subprocess
import time
from uuid import uuid4

import cv2
import numpy as np
import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.db.session import get_db
from app.intelligence.contracts import ANALYZER_VERSION
from app.main import app
from app.models.entities import AnalysisJob, EvaluationSession, IdempotencyRecord, MediaAsset, TrainingSession, UploadReservation, now
from app.repositories.evaluations import EvaluationRepository
from app.repositories.jobs import JobRepository
from app.services.cleanup import cleanup_once
from app.services.storage import LocalStorage
from app.services.worker import Worker


@pytest.fixture
def uploads(client, member, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "media_root", str(tmp_path / "private"))
    path = tmp_path / "video.mp4"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (64, 64))
    assert writer.isOpened()
    for _ in range(20):
        writer.write(np.zeros((64, 64, 3), dtype=np.uint8))
    writer.release()
    factory = contextmanager(app.dependency_overrides[get_db])
    return path.read_bytes(), factory


def upload(client, member, payload, key="upload-1", slug="pukulan", retry=None, filename="video.mp4", mime="video/mp4"):
    data = {"movementSlug": slug}
    if retry is not None:
        data["retryOf"] = retry
    return client.post("/api/v1/member/sessions", headers={**member, "Idempotency-Key": key},
                       data=data, files={"video": (filename, payload, mime)})


def analysis_result():
    return {"movement": "pukulan", "matched_variant": None, "reference_profile_id": None,
            "score": None, "status": "reference_not_ready", "pose_status": "not_detected",
            "analysis": {"frames_processed": 1, "valid_pose_frames": 0, "key_frame": None,
                         "key_frame_time": None, "method": "static-reference-pose"},
            "issues": [], "model": {"analyzer_version": ANALYZER_VERSION, "reference_version": None}}


def assert_no_upload_state(factory):
    with factory() as db:
        for table in [TrainingSession, AnalysisJob, MediaAsset, IdempotencyRecord, UploadReservation]:
            assert db.scalar(select(func.count()).select_from(table)) == 0
    assert list(LocalStorage().candidates()) == []


def test_upload_persists_verified_metadata_and_returns_owned_session(client, member, uploads):
    video, factory = uploads
    response = upload(client, member, video, filename="../../private.mp4")
    assert response.status_code == 202, response.text
    accepted = response.json()
    assert accepted["processingStatus"] == "queued" and accepted["uploadedAt"].endswith("Z")
    status = client.get(accepted["statusUrl"], headers=member)
    assert status.status_code == 200, status.text
    body = status.json()
    assert body["processingStatus"] == "queued" and body["analysisStatus"] is None
    assert body["evaluationId"] is None and body["reviewAvailable"] is False
    assert body["media"]["status"] == "available" and body["media"]["durationSeconds"] == 2
    assert body["media"]["width"] == body["media"]["height"] == 64
    assert body["media"]["byteSize"] == len(video)
    assert body["media"]["playbackPath"] == accepted["statusUrl"] + "/video"
    assert "storage_key" not in status.text and settings.media_root not in status.text
    assert status.headers["cache-control"] == "no-store"
    with factory() as db:
        media = db.scalar(select(MediaAsset))
        session = db.scalar(select(TrainingSession))
        assert media.expires_at - session.uploaded_at == timedelta(hours=24)
        assert LocalStorage().exists(media.storage_key)
        assert db.scalar(select(AnalysisJob)).attempt == 0
        assert db.scalar(select(func.count()).select_from(UploadReservation)) == 0
    other = client.post("/api/v1/auth/sign-up", json={
        "fullName": "Other Member", "identifier": "other@example.com", "password": "password123",
    }).json()
    assert client.get(accepted["statusUrl"], headers={"Authorization": "Bearer " + other["accessToken"]}).status_code == 404
    assert client.get(accepted["statusUrl"]).status_code == 401
    assert client.get("/api/v1/member/sessions/not-an-id", headers=member).status_code == 404


def test_upload_idempotency_replays_even_when_queue_is_full(client, member, uploads, monkeypatch):
    video, factory = uploads
    first = upload(client, member, video)
    assert first.status_code == 202
    monkeypatch.setattr(settings, "max_pending_sessions", 1)
    replay = upload(client, member, video)
    assert replay.status_code == 202 and replay.json() == first.json()
    conflict = upload(client, member, video + b"different")
    assert conflict.status_code == 409 and conflict.json()["code"] == "idempotency_conflict"
    assert upload(client, member, video, key="second").status_code == 429
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(TrainingSession)) == 1
        assert db.scalar(select(func.count()).select_from(AnalysisJob)) == 1
        assert db.scalar(select(func.count()).select_from(UploadReservation)) == 0
    assert len(list(LocalStorage().candidates())) == 1


@pytest.mark.parametrize("fault,status", [
    ("empty", 422), ("fake", 422), ("suffix", 415), ("wrong-container", 422),
    ("too-long", 422), ("resolution", 422), ("size", 413), ("slug", 404),
    ("missing-key", 422),
])
def test_bad_upload_leaves_no_files_jobs_or_quota(client, member, uploads, monkeypatch, fault, status):
    video, factory = uploads
    filename, mime, slug = "video.mp4", "video/mp4", "pukulan"
    if fault == "empty":
        video = b""
    elif fault == "fake":
        video = b"not a video"
    elif fault == "suffix":
        filename = "video.exe"
    elif fault == "wrong-container":
        filename, mime = "video.webm", "video/webm"
    elif fault == "too-long":
        monkeypatch.setattr(settings, "max_video_seconds", 1)
    elif fault == "resolution":
        monkeypatch.setattr(settings, "max_video_dimension", 32)
    elif fault == "size":
        monkeypatch.setattr(settings, "max_video_mb", 0)
    elif fault == "slug":
        slug = "kuda_kuda"
    if fault == "missing-key":
        response = client.post("/api/v1/member/sessions", headers=member, data={"movementSlug": slug},
                               files={"video": (filename, video, mime)})
    else:
        response = upload(client, member, video, slug=slug, filename=filename, mime=mime)
    assert response.status_code == status, response.text
    assert response.json()["requestId"] == response.headers["x-request-id"]
    assert_no_upload_state(factory)


def test_request_body_limit_catches_chunked_multipart_before_spooling(client, member, uploads, monkeypatch):
    _, factory = uploads
    monkeypatch.setattr(settings, "max_video_mb", 1)
    boundary = "test-boundary"
    def chunks():
        yield (f"--{boundary}\r\nContent-Disposition: form-data; name=\"video\"; filename=\"video.mp4\"\r\n"
               "Content-Type: video/mp4\r\n\r\n").encode()
        for _ in range(5):
            yield b"x" * (512 * 1024)
        yield f"\r\n--{boundary}--\r\n".encode()
    response = client.post("/api/v1/member/sessions", headers={**member, "Idempotency-Key": "big",
                           "Content-Type": f"multipart/form-data; boundary={boundary}"}, content=chunks())
    assert response.status_code == 413, response.text
    assert response.json()["code"] == "upload_too_large"
    assert_no_upload_state(factory)


def test_retry_of_must_belong_to_owner_and_category(client, member, uploads):
    video, factory = uploads
    first = upload(client, member, video).json()["sessionId"]
    assert upload(client, member, video, key="wrong-category", slug="tendangan", retry=first).status_code == 422
    second = upload(client, member, video, key="retry", retry=first)
    assert second.status_code == 202
    assert client.get(second.json()["statusUrl"], headers=member).json()["retryOf"] == first
    assert upload(client, member, video, key="unknown", retry="99999").status_code == 404


def test_claim_recovery_fencing_and_single_result(client, member, uploads):
    video, factory = uploads
    accepted = upload(client, member, video).json()
    jobs = JobRepository(factory)
    first = jobs.claim("worker-1")
    assert first and jobs.claim("worker-2") is None
    assert jobs.heartbeat(first)
    with factory() as db:
        db.get(AnalysisJob, first.job_id).lease_until = now() - timedelta(seconds=1)
        db.commit()
    restarted = JobRepository(factory)
    second = restarted.claim("restarted-worker")
    assert second and second.token != first.token
    assert not jobs.heartbeat(first) and not jobs.complete(first, analysis_result())
    assert restarted.complete(second, analysis_result())
    assert not restarted.complete(second, analysis_result())
    status = client.get(accepted["statusUrl"], headers=member).json()
    assert status["processingStatus"] == "completed" and status["analysisStatus"] == "reference_not_ready"
    with factory() as db:
        rows = db.scalars(select(EvaluationSession)).all()
        assert len(rows) == 1 and rows[0].score is None
        assert rows[0].result_json["model"]["feature_version"] == second.config["featureVersion"]
    assert client.get(accepted["evaluationUrl"], headers=member).json()["score"] is None


def test_result_and_completion_are_atomic(client, member, uploads, monkeypatch):
    video, factory = uploads
    accepted = upload(client, member, video).json()
    jobs = JobRepository(factory)
    claim = jobs.claim("worker")
    original = EvaluationRepository.build
    def fail_after_add(self, *args):
        original(self, *args)
        raise RuntimeError("simulated transaction failure")
    with monkeypatch.context() as patch:
        patch.setattr(EvaluationRepository, "build", fail_after_add)
        with pytest.raises(RuntimeError):
            jobs.complete(claim, analysis_result())
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(EvaluationSession)) == 0
    assert client.get(accepted["statusUrl"], headers=member).json()["processingStatus"] == "processing"
    assert jobs.complete(claim, analysis_result())


def test_retry_only_transient_and_bounded(client, member, uploads):
    video, factory = uploads
    accepted = upload(client, member, video).json()
    jobs = JobRepository(factory)
    for attempt in range(1, 4):
        claim = jobs.claim("worker")
        assert claim
        assert jobs.fail(claim, "temporary_io", transient=True)
        with factory() as db:
            job = db.get(AnalysisJob, claim.job_id)
            assert job.attempt == attempt
            if attempt < 3:
                assert job.state == "queued" and jobs.claim("too-soon") is None
                job.available_at = now() - timedelta(seconds=1)
                db.commit()
            else:
                assert job.state == "failed"
    status = client.get(accepted["statusUrl"], headers=member).json()
    assert status["processingStatus"] == "failed" and status["error"]["code"] == "retry_exhausted"


def test_expired_media_rejected_without_worker_and_results_survive_cleanup(client, member, uploads):
    video, factory = uploads
    accepted = upload(client, member, video).json()
    jobs = JobRepository(factory)
    assert jobs.complete(jobs.claim("worker"), analysis_result())
    with factory() as db:
        db.scalar(select(MediaAsset)).expires_at = now() - timedelta(seconds=1)
        db.commit()
    status = client.get(accepted["statusUrl"], headers=member).json()
    assert status["media"]["status"] == "expired"
    assert cleanup_once(factory) == 1
    assert cleanup_once(factory) == 0
    status = client.get(accepted["statusUrl"], headers=member).json()
    assert status["processingStatus"] == "completed" and status["evaluationId"] is not None
    assert status["media"]["status"] == "expired"
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(EvaluationSession)) == 1


def test_cleanup_fences_active_job_before_unlink(client, member, uploads):
    video, factory = uploads
    accepted = upload(client, member, video).json()
    jobs = JobRepository(factory)
    claim = jobs.claim("worker")
    with factory() as db:
        db.scalar(select(MediaAsset)).expires_at = now() - timedelta(seconds=1)
        db.commit()
    assert cleanup_once(factory) == 0
    assert LocalStorage().exists(claim.storage_key)
    assert not jobs.heartbeat(claim) and not jobs.complete(claim, analysis_result())
    with factory() as db:
        db.get(AnalysisJob, claim.job_id).lease_until = now() - timedelta(seconds=1)
        db.commit()
    assert cleanup_once(factory) == 1
    status = client.get(accepted["statusUrl"], headers=member).json()
    assert status["processingStatus"] == "failed" and status["error"]["code"] == "media_expired"


def test_cleanup_orphans_and_crashed_upload_reservations(client, member, uploads):
    video, factory = uploads
    accepted = upload(client, member, video).json()
    storage = LocalStorage()
    owner = int(client.get("/api/v1/auth/session", headers=member).json()["id"])
    token = uuid4().hex
    key = f"objects/{token}.mp4"
    with storage.create(storage.staging_key(key)) as stream:
        stream.write(b"partial")
    with factory() as db:
        db.add(UploadReservation(id=token, user_id=owner, storage_key=key, reserved_bytes=100,
                                 expires_at=now() - timedelta(seconds=1)))
        db.commit()
    orphan = f"objects/{uuid4().hex}.mp4"
    with storage.create(orphan) as stream:
        stream.write(b"orphan")
    os.utime(storage.path(orphan), (time.time() - 7200, time.time() - 7200))
    cleanup_once(factory)
    assert not storage.exists(orphan) and not storage.exists(storage.staging_key(key))
    assert client.get(accepted["statusUrl"], headers=member).json()["media"]["status"] == "available"
    with pytest.raises(ValueError):
        storage.path("../../outside")
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(UploadReservation)) == 0


def test_expired_queued_job_and_exhausted_crash_recovery(client, member, uploads):
    video, factory = uploads
    accepted = upload(client, member, video).json()
    with factory() as db:
        db.scalar(select(MediaAsset)).expires_at = now() - timedelta(seconds=1)
        db.commit()
    assert JobRepository(factory).claim("worker") is None
    assert client.get(accepted["statusUrl"], headers=member).json()["error"]["code"] == "media_expired"


def test_reference_snapshot_survives_artifact_changes(client, member, uploads, monkeypatch, tmp_path):
    import json
    from app.models.entities import ReferenceProfile
    from app.intelligence.contracts import FEATURE_VERSION
    video, factory = uploads
    monkeypatch.setattr(settings, "reference_root", str(tmp_path))
    reference = {"movement": "pukulan", "variant": "test-only", "version": "fixture-v1",
                 "feature_version": FEATURE_VERSION,
                 "feature_statistics": {str(i): {"median": 10, "iqr": 2} for i in range(8)}}
    path = tmp_path / "reference.json"
    path.write_text(json.dumps(reference), encoding="utf-8")
    with factory() as db:
        db.add(ReferenceProfile(movement="pukulan", variant="test-only", version="fixture-v1",
                                 artifact_path="reference.json", evaluator_type="static-reference-pose"))
        db.commit()
    assert upload(client, member, video).status_code == 202
    path.write_text("invalid replacement", encoding="utf-8")
    claim = JobRepository(factory).claim("restarted-worker")
    assert claim.references[0]["profile"]["version"] == "fixture-v1"
    assert claim.references[0]["checksum"]


def test_commit_failure_removes_finalized_candidate_without_job(client, member, uploads, monkeypatch):
    from sqlalchemy.orm import Session
    video, factory = uploads
    original = Session.commit
    def fail_acceptance_commit(self):
        if any(isinstance(row, IdempotencyRecord) for row in self.new):
            raise OSError("simulated commit failure")
        return original(self)
    with monkeypatch.context() as patch:
        patch.setattr(Session, "commit", fail_acceptance_commit)
        response = upload(client, member, video)
    assert response.status_code == 500
    assert_no_upload_state(factory)


def test_missing_media_and_permanent_errors_do_not_retry(client, member, uploads):
    video, factory = uploads
    accepted = upload(client, member, video).json()
    with factory() as db:
        key = db.scalar(select(MediaAsset.storage_key))
    LocalStorage().delete(key)
    assert Worker(factory, "worker").run_once()
    body = client.get(accepted["statusUrl"], headers=member).json()
    assert body["processingStatus"] == "failed" and body["error"]["code"] == "media_unavailable"
    assert JobRepository(factory).claim("another-worker") is None


def test_crash_recovery_attempt_cap(client, member, uploads):
    video, factory = uploads
    accepted = upload(client, member, video).json()
    jobs = JobRepository(factory)
    claim = jobs.claim("crashed-worker")
    with factory() as db:
        job = db.get(AnalysisJob, claim.job_id)
        job.attempt = settings.worker_max_attempts
        job.lease_until = now() - timedelta(seconds=1)
        db.commit()
    assert jobs.claim("restarted-worker") is None
    assert client.get(accepted["statusUrl"], headers=member).json()["error"]["code"] == "retry_exhausted"


@pytest.mark.skipif(not Path(settings.pose_model_path).is_file(), reason="Local ignored MediaPipe model unavailable")
def test_real_inference_child_on_blank_video_keeps_null_score(client, member, uploads):
    video, factory = uploads
    accepted = upload(client, member, video).json()
    assert Worker(factory, "real-inference-test").run_once()
    status = client.get(accepted["statusUrl"], headers=member).json()
    assert status["processingStatus"] == "completed", status
    assert status["analysisStatus"] == "reference_not_ready"
    with factory() as db:
        result = db.scalar(select(EvaluationSession))
        assert result.score is None and result.result_json["analysis"]["frames_processed"] > 0


def test_supervised_timeout_kills_child_and_fails_job(client, member, uploads, monkeypatch):
    from app.services import worker
    video, factory = uploads
    accepted = upload(client, member, video).json()
    original = subprocess.Popen
    def slow_child(command, **kwargs):
        return original([command[0], "-c", "import sys,time; sys.stdin.read(); time.sleep(10)"], **kwargs)
    monkeypatch.setattr(worker.subprocess, "Popen", slow_child)
    monkeypatch.setattr(settings, "worker_job_timeout_seconds", 0.15)
    assert Worker(factory, "timeout-worker").run_once()
    status = client.get(accepted["statusUrl"], headers=member).json()
    assert status["processingStatus"] == "failed" and status["error"]["code"] == "analysis_timeout"
