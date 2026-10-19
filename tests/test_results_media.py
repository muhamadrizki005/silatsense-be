from datetime import timedelta
import io
import anyio

import numpy as np
import pytest
from sqlalchemy import select, func

from app.intelligence.contracts import Pose, FEATURE_VERSION
from app.intelligence.features.biomechanics import BiomechanicalFeatures
from app.intelligence.preprocessing.landmarks import VisibleLandmarkPreprocessor
from app.intelligence.features.presentation import measurements, raw_pose
from app.models.entities import AnalysisJob, CoachNote, EvaluationSession, MediaAsset, TrainingSession, User, now
from app.repositories.evaluations import EvaluationRepository
from app.repositories.jobs import JobRepository
from app.services.analysis import EvaluationService
from app.services.cleanup import cleanup_once
from app.services.media import PrivateVideoResponse, stream_chunks
from app.services.storage import LocalStorage
from test_sessions_jobs import uploads, upload, analysis_result


@pytest.fixture
def accepted(client, member, uploads):
    payload, factory = uploads
    result = upload(client, member, payload)
    assert result.status_code == 202, result.text
    return result.json()["statusUrl"], payload, factory


def finish(factory):
    jobs = JobRepository(factory)
    claim = jobs.claim("phase4-test")
    result = analysis_result()
    assert jobs.complete(claim, result)


def test_evaluation_pending_failed_and_owner_isolation(client, member, accepted):
    path, _, factory = accepted
    for tail in ("evaluation", "pose", "acknowledge"):
        response = (client.post if tail == "acknowledge" else client.get)(path + "/" + tail, headers=member)
        assert response.status_code == 409 and response.json()["code"] == "evaluation_pending"
    other = client.post("/api/v1/auth/sign-up", json={
        "fullName": "Another Member", "identifier": "another@example.com", "password": "password123",
    }).json()
    headers = {"Authorization": "Bearer " + other["accessToken"]}
    for tail in ("evaluation", "pose", "video"):
        assert client.get(path + "/" + tail, headers=headers).status_code == 404
        assert client.get(path + "/" + tail).status_code == 401
    assert client.delete(path, headers=headers).status_code == 404
    jobs = JobRepository(factory)
    assert jobs.fail(jobs.claim("test"), "analysis_failed")
    for tail in ("evaluation", "pose"):
        response = client.get(path + "/" + tail, headers=member)
        assert response.status_code == 409 and response.json()["code"] == "analysis_failed"


def test_completed_null_evaluation_pose_and_acknowledge(client, member, accepted):
    path, _, factory = accepted
    finish(factory)
    response = client.get(path + "/evaluation", headers=member)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["sessionId"] == path.split("/")[-1] and isinstance(data["id"], str)
    assert data["score"] is None and data["scoreReason"] == "reference_not_ready"
    assert data["featureVersion"] == FEATURE_VERSION and data["keyFrame"] is None
    assert data["validRepetitions"] is None and data["deviatedRepetitions"] is None
    assert data["measurements"] == [] and "measurements_not_stored" in data["unavailableReasons"]
    assert data["evaluatedAt"].endswith("Z")
    assert response.headers["cache-control"] == "no-store" and response.headers["x-request-id"]
    assert client.get(path + "/pose", headers=member).json() == {
        "sessionId": path.split("/")[-1], "pose": None, "reason": "pose_not_stored",
    }
    first = client.post(path + "/acknowledge", headers=member)
    assert first.status_code == 200
    assert client.post(path + "/acknowledge", headers=member).json() == first.json()
    assert client.get(path, headers=member).json()["acknowledgedAt"] == first.json()["acknowledgedAt"]


@pytest.mark.parametrize("header,slice_,status", [
    (None, slice(None), 200), ("bytes=0-9", slice(0, 10), 206),
    ("bytes=10-", slice(10, None), 206), ("bytes=-10", slice(-10, None), 206),
    ("bytes=0-999999", slice(None), 206), ("bytes=-999999", slice(None), 206),
])
def test_video_full_and_single_ranges(client, member, accepted, header, slice_, status):
    path, payload, _ = accepted
    headers = {**member, **({"Range": header} if header else {})}
    response = client.get(path + "/video", headers=headers)
    assert response.status_code == status, response.text
    assert response.content == payload[slice_]
    assert int(response.headers["content-length"]) == len(payload[slice_])
    assert response.headers["content-type"] == "video/mp4"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    if status == 206:
        assert response.headers["content-range"].endswith(f"/{len(payload)}")


@pytest.mark.parametrize("header", ["bytes=999999-", "bytes=5-2", "bytes=-0", "bytes=-",
                                      "bytes=0-1,3-4", "items=0-1", "bytes=a-b", "bytes=" + "9" * 30 + "-"])
def test_invalid_range_has_domain_error(client, member, accepted, header):
    path, payload, _ = accepted
    response = client.get(path + "/video", headers={**member, "Range": header})
    assert response.status_code == 416, response.text
    assert response.json()["code"] == "invalid_range" and response.json()["requestId"]
    assert response.headers["content-range"] == f"bytes */{len(payload)}"


def test_expiry_exact_boundary_blocks_video_preserves_evaluation(client, member, accepted, monkeypatch):
    path, _, factory = accepted
    finish(factory)
    with factory() as db:
        expiry = db.scalar(select(MediaAsset.expires_at))
    monkeypatch.setattr("app.services.media.now", lambda: expiry)
    response = client.get(path + "/video", headers={**member, "Range": "bytes=0-1"})
    assert response.status_code == 410 and response.json()["code"] == "media_expired"
    assert client.get(path + "/evaluation", headers=member).status_code == 200
    assert client.post(path + "/acknowledge", headers=member).status_code == 200
    with factory() as db:
        assert db.scalar(select(MediaAsset.expires_at)) == expiry


@pytest.mark.parametrize("change", ["delete", "revoke", "expire", "db-down"])
def test_stream_stops_after_access_change_and_closes_handle(client, member, accepted, monkeypatch, change):
    path, _, factory = accepted
    with factory() as db:
        media = db.scalar(select(MediaAsset))
        args = (media.user_id, 0, media.session_id, media.id, media.expires_at)
    monkeypatch.setattr("app.services.media.CHUNK_SIZE", 4)
    handle = io.BytesIO(b"1234567890")
    chunks = stream_chunks(handle, 0, 9, factory, *args)
    assert next(chunks) == b"1234"
    if change == "db-down":
        monkeypatch.setattr("app.services.media.stream_allowed", lambda *a: (_ for _ in ()).throw(OSError()))
    else:
        with factory() as db:
            if change == "delete":
                db.get(TrainingSession, args[2]).deleted_at = now()
            elif change == "revoke":
                db.get(User, args[0]).auth_version += 1
            else:
                db.get(MediaAsset, args[3]).expires_at = now()
            db.commit()
    assert list(chunks) == [] and handle.closed


def test_delete_fences_active_worker_and_cleanup_waits_for_reader(client, member, accepted):
    path, _, factory = accepted
    jobs = JobRepository(factory)
    claim = jobs.claim("running")
    assert client.delete(path, headers=member).status_code == 204
    assert client.delete(path, headers=member).status_code == 204
    assert not jobs.heartbeat(claim) and not jobs.complete(claim, analysis_result())
    assert cleanup_once(factory) == 0 and LocalStorage().exists(claim.storage_key)
    with factory() as db:
        job = db.scalar(select(AnalysisJob))
        assert job.claim_token is None and job.state == "failed"
        job.lease_until = now() - timedelta(seconds=1)
        db.commit()
    assert cleanup_once(factory) == 1
    assert cleanup_once(factory) == 0 and not LocalStorage().exists(claim.storage_key)
    for tail in ("", "/video", "/evaluation", "/pose"):
        assert client.get(path + tail, headers=member).status_code == 404


def test_delete_completed_retains_audit_hides_legacy_and_statistics(client, member, accepted):
    path, _, factory = accepted
    finish(factory)
    eid = client.get(path + "/evaluation", headers=member).json()["id"]
    assert client.get("/api/v1/member/profile", headers=member).json()["statistics"]["completedSessionCount"] == 1
    coach = client.post("/api/v1/auth/login", json={"email": "coach@example.com", "password": "password123"}).json()
    coach_headers = {"Authorization": "Bearer " + coach["access_token"]}
    from app.services.assignments import assign_coach
    with factory() as db:
        assign_coach(db, db.scalar(select(TrainingSession.user_id)), coach["user"]["id"], "test-admin", "Audit access")
    assert client.post(f"/api/v1/coach/evaluations/{eid}/notes", headers=coach_headers,
                       json={"note": "Audit note"}).status_code == 201
    assert client.delete(path, headers=member).status_code == 204
    assert client.get(f"/api/v1/evaluations/{eid}", headers=member).status_code == 404
    assert client.get("/api/v1/evaluations", headers=member).json() == []
    assert client.post(path + "/acknowledge", headers=member).status_code == 404
    assert client.get(f"/api/v1/evaluations/{eid}", headers=coach_headers).status_code == 404
    assert client.post(f"/api/v1/coach/evaluations/{eid}/notes", headers=coach_headers,
                       json={"note": "After deletion"}).status_code == 404
    statistics = client.get("/api/v1/member/profile", headers=member).json()["statistics"]
    assert statistics["completedSessionCount"] == 0 and statistics["totalDurationSeconds"] == 0
    assert cleanup_once(factory) == 1
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(EvaluationSession)) == 1
        assert db.scalar(select(func.count()).select_from(CoachNote)) == 1
        assert db.scalar(select(TrainingSession.processing_status)) == "completed"
    # Reusing upload's old key must not resurrect a deleted session.
    assert upload(client, member, accepted[1]).status_code == 409


def test_legacy_result_missing_raw_data_and_video(client, member, uploads):
    _, factory = uploads
    owner = client.get("/api/v1/auth/me", headers=member).json()["id"]
    with factory() as db:
        row = EvaluationRepository(db).save(owner, analysis_result())
        path = f"/api/v1/member/sessions/{row.training_session_id}"
    result = client.get(path + "/evaluation", headers=member)
    assert result.status_code == 200, result.text
    assert result.json()["featureVersion"] is None
    assert "feature_version_not_stored" in result.json()["unavailableReasons"]
    response = client.get(path + "/video", headers=member)
    assert response.status_code == 410 and response.json()["code"] == "media_unavailable"


def test_missing_private_file_never_exposes_path(client, member, accepted):
    path, _, factory = accepted
    with factory() as db:
        key = db.scalar(select(MediaAsset.storage_key))
    LocalStorage().delete(key)
    response = client.get(path + "/video", headers=member)
    assert response.status_code == 410 and key not in response.text
    assert client.get(path, headers=member).json()["media"]["playbackPath"] is None


def test_analysis_persists_best_pose_and_measurements_without_changing_score():
    points = np.random.default_rng(15).random((33, 4))
    points[:, 3] = 1
    pose = Pose(points)
    features = BiomechanicalFeatures().extract(VisibleLandmarkPreprocessor().normalize(pose))
    profile = {"feature_version": FEATURE_VERSION, "version": "test-v1", "variant": "test",
               "feature_statistics": {name: {"median": value, "iqr": 1} for name, value in features.items()}}
    class Extractor:
        def extract(self, rgb):
            return pose
        def close(self):
            pass
    rgb = np.zeros((100, 200, 3), dtype=np.uint8)
    service = EvaluationService(extractor_factory=Extractor, frame_source=lambda *a: [(10, 1.0, rgb)])
    result = service.analyze(None, "pukulan", [profile])
    assert result["score"] == 100 and result["status"] == "experimental"
    assert len(result["measurements"]) == 20
    assert all(m["assessment"] == "within_reference" and m["deviation"] == 0 for m in result["measurements"])
    assert result["pose"]["landmarks"][11]["x"] == pytest.approx(points[11, 0] / 2)
    assert result["pose"]["landmarks"][11]["y"] == points[11, 1]
    assert result["pose"]["imageWidth"] == 200 and result["analysis"]["key_frame"] == 10
    result = service.analyze(None, "pukulan", [])
    assert result["score"] is None and result["pose"] is not None
    assert all(m["assessment"] == "not_assessed" for m in result["measurements"])


def test_stored_pose_and_measurements_are_returned_after_video_cleanup(client, member, accepted):
    path, _, factory = accepted
    jobs = JobRepository(factory)
    claim = jobs.claim("test")
    result = analysis_result()
    result["pose_status"] = "detected"
    result["pose"] = raw_pose(Pose(np.ones((33, 4))), np.zeros((100, 200, 3)), 10, 1.0)
    result["measurements"] = measurements({"left_elbow_angle": 90})
    result["analysis"].update(key_frame=10, key_frame_time=1.0, valid_pose_frames=1)
    assert jobs.complete(claim, result)
    first = client.get(path + "/evaluation", headers=member).json()
    pose = client.get(path + "/pose", headers=member).json()
    assert pose["pose"] == result["pose"] and pose["reason"] is None
    assert first["keyFrame"] == {"index": 10, "timeSeconds": 1.0}
    assert first["measurements"] == result["measurements"]
    assert first["issues"] == []  # Empty issues cannot imply a comparison succeeded.
    with factory() as db:
        db.scalar(select(MediaAsset)).expires_at = now()
        db.commit()
    assert cleanup_once(factory) == 1
    assert client.get(path + "/evaluation", headers=member).json() == first
    assert client.get(path + "/pose", headers=member).json() == pose


@pytest.mark.parametrize("kind", ["revoked", "expiry", "expiry-slow-db"])
def test_watchdog_closes_stalled_stream_within_one_second(kind):
    handle = io.BytesIO(b"abc")
    sent = []
    async def scenario():
        def access_check():
            if kind == "expiry-slow-db":
                import time
                time.sleep(2)
            return kind != "revoked"
        response = PrivateVideoResponse(iter([b"abc", b"def"]), handle=handle,
            expiry=now() + timedelta(seconds=0.05 if kind == "expiry" else 0.6 if kind == "expiry-slow-db" else 10),
            access_check=access_check)
        async def send(message):
            if message["type"] == "http.response.body" and message.get("body"):
                sent.append(message["body"])
                await anyio.sleep(5)  # Simulate a client stalled on network send.
        async def receive():
            await anyio.sleep(5)
        with anyio.fail_after(1):
            await response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send)
    anyio.run(scenario)
    assert sent == [b"abc"] and handle.closed


def test_measurement_units_threshold_missing_features_and_invalid_landmarks():
    features = {"left_elbow_angle": 12, "stance_width_ratio": 2.5}
    profile = {"feature_statistics": {"left_elbow_angle": {"median": 10, "iqr": 2}}}
    rows = {r["feature"]: r for r in measurements(features, profile, features)}
    assert rows["left_elbow_angle"]["assessment"] == "deviates"
    assert rows["left_elbow_angle"]["unit"] == "deg"
    assert rows["stance_width_ratio"]["unit"] == "shoulder_width"
    assert rows["right_knee_angle"]["value"] is None
    assert rows["right_knee_angle"]["reason"] == "feature_unavailable"
    points = np.ones((33, 4))
    points[0, 0] = np.nan
    points[1, 3] = 2
    data = raw_pose(Pose(points), np.zeros((100, 200, 3)), 0, 0)
    assert [p["index"] for p in data["landmarks"]] == list(range(2, 33))


def test_best_frame_measurements_and_pose_match_selected_reference():
    points = np.random.default_rng(7).random((33, 4))
    points[:, 3] = 1
    second = Pose(points)
    first_points = points.copy()
    first_points[13, :2] += 1
    first = Pose(first_points)
    values = BiomechanicalFeatures().extract(VisibleLandmarkPreprocessor().normalize(second))
    profile = {"feature_version": FEATURE_VERSION, "version": "fixed-v1", "variant": "known",
               "feature_statistics": {name: {"median": value, "iqr": 0.5} for name, value in values.items()}}
    poses = iter([first, second])
    class Extractor:
        def extract(self, rgb):
            return next(poses)
        def close(self):
            pass
    rgb = np.zeros((100, 200, 3), dtype=np.uint8)
    result = EvaluationService(extractor_factory=Extractor,
        frame_source=lambda *a: [(0, 0, rgb), (20, 2, rgb)]).analyze(None, "pukulan", [profile])
    assert result["analysis"]["key_frame"] == 20 and result["pose"]["frameIndex"] == 20
    assert result["model"]["reference_version"] == "fixed-v1" and result["score"] == 100
    assert result["pose"]["landmarks"][13]["x"] == pytest.approx(points[13, 0] / 2)
    assert all(m["value"] == m["referenceMedian"] for m in result["measurements"])


def test_video_coach_and_origin_restrictions_and_cors(client, member, accepted):
    path, _, _ = accepted
    coach = client.post("/api/v1/auth/login", json={"email": "coach@example.com", "password": "password123"}).json()
    headers = {"Authorization": "Bearer " + coach["access_token"]}
    assert client.get(path + "/video", headers=headers).status_code == 403
    assert client.delete(path, headers={**member, "Origin": "https://evil.example"}).status_code == 403
    from app.core.config import settings
    response = client.options(path, headers={"Origin": settings.frontend_origin,
        "Access-Control-Request-Method": "DELETE", "Access-Control-Request-Headers": "Authorization,Range"})
    assert response.status_code == 200
    assert "DELETE" in response.headers["access-control-allow-methods"]
