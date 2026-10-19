from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import timedelta
import os
from threading import Barrier, Event

import cv2
from fastapi.testclient import TestClient
import numpy as np
import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.db.session import get_db
from app.intelligence.contracts import ANALYZER_VERSION
from app.main import app
from app.models.entities import AnalysisJob, EvaluationSession, MediaAsset, TrainingSession, UploadReservation, now
from app.repositories.jobs import JobRepository
from app.services.storage import LocalStorage


def test_delete_racing_worker_completion_preserves_only_committed_result(client, member, concurrent_uploads):
    video, factory = concurrent_uploads
    response = request_upload(member, video, "delete-race")
    path = response.json()["statusUrl"]
    jobs = JobRepository(factory)
    claim = jobs.claim("finishing-worker")
    from test_sessions_jobs import analysis_result
    barrier = Barrier(2)
    def complete():
        barrier.wait(timeout=10)
        return jobs.complete(claim, analysis_result())
    def remove():
        with TestClient(app) as other:
            barrier.wait(timeout=10)
            return other.delete(path, headers=member)
    with ThreadPoolExecutor(max_workers=2) as pool:
        completion, deletion = pool.submit(complete), pool.submit(remove)
        committed = completion.result(timeout=20)
        assert deletion.result(timeout=20).status_code == 204
    assert client.get(path, headers=member).status_code == 404
    assert not jobs.heartbeat(claim)
    with factory() as db:
        assert db.scalar(select(TrainingSession)).deleted_at is not None
        assert db.scalar(select(MediaAsset)).deletion_requested_at is not None
        assert db.scalar(select(func.count()).select_from(EvaluationSession)) == int(committed)


def test_parallel_acknowledge_returns_one_timestamp(client, member, concurrent_uploads):
    video, factory = concurrent_uploads
    path = request_upload(member, video, "ack-race").json()["statusUrl"]
    from test_sessions_jobs import analysis_result
    jobs = JobRepository(factory)
    assert jobs.complete(jobs.claim("worker"), analysis_result())
    barrier = Barrier(2)
    def acknowledge():
        with TestClient(app) as other:
            barrier.wait(timeout=10)
            return other.post(path + "/acknowledge", headers=member)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = [future.result(timeout=20) for future in [pool.submit(acknowledge), pool.submit(acknowledge)]]
    assert [r.status_code for r in responses] == [200, 200]
    assert responses[0].json() == responses[1].json()

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL", "").startswith("mysql"),
    reason="Persistent queue races require disposable MySQL row locks",
)


@pytest.fixture
def concurrent_uploads(client, member, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "media_root", str(tmp_path / "private"))
    path = tmp_path / "video.mp4"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (32, 32))
    assert writer.isOpened()
    for _ in range(5):
        writer.write(np.zeros((32, 32, 3), dtype=np.uint8))
    writer.release()
    return path.read_bytes(), contextmanager(app.dependency_overrides[get_db])


def request_upload(member, video, key, barrier=None):
    with TestClient(app, raise_server_exceptions=False) as other:
        if barrier:
            barrier.wait(timeout=10)
        return other.post("/api/v1/member/sessions", headers={**member, "Idempotency-Key": key},
                          data={"movementSlug": "pukulan"}, files={"video": ("video.mp4", video, "video/mp4")})


def test_simultaneous_identical_upload_has_one_session_and_one_file(client, member, concurrent_uploads):
    video, factory = concurrent_uploads
    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(request_upload, member, video, "same-key", barrier) for _ in range(2)]
        responses = [future.result(timeout=30) for future in futures]
    assert [response.status_code for response in responses] == [202, 202], [response.text for response in responses]
    assert responses[0].json() == responses[1].json()
    with factory() as db:
        for table in [TrainingSession, AnalysisJob, MediaAsset]:
            assert db.scalar(select(func.count()).select_from(table)) == 1
        assert db.scalar(select(func.count()).select_from(UploadReservation)) == 0
    assert len(list(LocalStorage().candidates())) == 1


@pytest.mark.parametrize("limit", ["queue", "bytes"])
def test_concurrent_upload_cannot_exceed_reserved_quota(client, member, concurrent_uploads, monkeypatch, limit):
    video, factory = concurrent_uploads
    if limit == "queue":
        monkeypatch.setattr(settings, "max_pending_sessions", 1)
    else:
        monkeypatch.setattr(settings, "upload_quota_mb", 1)
        video += b"\0" * 600000
    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(request_upload, member, video, f"key-{i}", barrier) for i in range(2)]
        responses = [future.result(timeout=30) for future in futures]
    assert sorted(response.status_code for response in responses) == [202, 429], [response.text for response in responses]
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(TrainingSession)) == 1
        assert db.scalar(select(func.count()).select_from(UploadReservation)) == 0


def test_two_workers_claim_and_complete_once(client, member, concurrent_uploads):
    video, factory = concurrent_uploads
    assert request_upload(member, video, "job").status_code == 202
    jobs = JobRepository(factory)
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(jobs.claim, ["worker-1", "worker-2"]))
    assert sum(claim is not None for claim in claims) == 1
    stale = next(claim for claim in claims if claim)
    with factory() as db:
        db.get(AnalysisJob, stale.job_id).lease_until = now() - timedelta(seconds=1)
        db.commit()
    current = JobRepository(factory).claim("restarted-worker")
    assert current and current.token != stale.token
    def result():
        return {"movement": "pukulan", "matched_variant": None, "reference_profile_id": None,
                "score": None, "status": "reference_not_ready", "pose_status": "not_detected",
                "analysis": {"frames_processed": 1, "valid_pose_frames": 0, "key_frame": None},
                "issues": [], "model": {"analyzer_version": ANALYZER_VERSION, "reference_version": None}}
    assert not jobs.complete(stale, result())
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: jobs.complete(current, result()), range(2)))
    assert sorted(outcomes) == [False, True]
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(EvaluationSession)) == 1


def test_password_revocation_during_upload_prevents_job_commit(client, member, concurrent_uploads, monkeypatch):
    from app.services import sessions
    video, factory = concurrent_uploads
    validating, release = Event(), Event()
    original = sessions.probe_video
    def held_probe(path, suffix):
        result = original(path, suffix)
        validating.set()
        assert release.wait(timeout=10)
        return result
    monkeypatch.setattr(sessions, "probe_video", held_probe)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(request_upload, member, video, "revoked-during-upload")
        assert validating.wait(timeout=10)
        changed = client.patch("/api/v1/member/password", headers=member, json={
            "currentPassword": "password123", "newPassword": "changed-password123",
        })
        release.set()
        assert changed.status_code == 204
        response = pending.result(timeout=20)
    assert response.status_code == 401, response.text
    with factory() as db:
        for table in [TrainingSession, AnalysisJob, MediaAsset, UploadReservation]:
            assert db.scalar(select(func.count()).select_from(table)) == 0
    assert list(LocalStorage().candidates()) == []
