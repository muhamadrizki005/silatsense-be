"""Temporal worker/API contracts, isolation and failure cases, without private data."""

import copy
import hashlib
import json

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.intelligence.coach_contracts import ANALYZER_VERSION, FEATURE_VERSION
from app.intelligence.coach_reference import fit
from app.models.entities import AnalysisJob, TrainingSession
from app.services.assignments import assign_coach
from app.repositories.jobs import JobRepository
from app.services.analysis_process import execute
from app.services.coach_analysis import (
    ReferenceArtifactError,
    analyze,
    load_reference,
    timeline,
)
from test_coach_reference import dataset, report, sample
from test_sessions_jobs import uploads  # noqa: F401
from test_b2_uploads import remote, initiate, put, finish, request_body  # noqa: F401


@pytest.fixture
def temporal(tmp_path, monkeypatch):
    model = fit(dataset([sample(f"reference-{i}", i) for i in range(3)]))
    path = tmp_path / "reference.json"
    path.write_text(json.dumps(model), encoding="utf-8")
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(settings, "analysis_mode", "coach-reference")
    monkeypatch.setattr(settings, "coach_reference_model_path", str(path))
    monkeypatch.setattr(settings, "coach_reference_sha256", checksum)
    observed = report("held-out", 1)
    observed["video"].update(imageWidth=1280, imageHeight=720)
    for row in observed["frames"]:
        row["imageLandmarks"] = [[0.8, 0.5, 0.9] for _ in range(33)]
    monkeypatch.setattr(
        "app.intelligence.movement_video.extract_video",
        lambda *a, **kw: copy.deepcopy(observed),
    )
    return model, checksum, observed


def post_local(client, member, payload, target="pukulan_depan", key="temporal"):
    data = {"movementSlug": "pukulan"}
    if target is not None:
        data["movementId"] = target
    return client.post(
        "/api/v1/member/sessions",
        headers={**member, "Idempotency-Key": key},
        data=data,
        files={"video": ("video.mp4", payload, "video/mp4")},
    )


@pytest.mark.parametrize(
    "target,code",
    [
        (None, "movement_id_required"),
        ("tendangan_t", "invalid_movement_id"),
        ("unknown", "invalid_movement_id"),
    ],
)
def test_target_is_explicit_and_matches_category(
    client, member, uploads, temporal, target, code
):
    response = post_local(client, member, uploads[0], target)
    assert response.status_code == 422 and response.json()["code"] == code
    with uploads[1]() as db:
        assert db.scalar(select(AnalysisJob)) is None


def test_missing_reference_checksum_is_configuration_error(
    client, member, uploads, temporal, monkeypatch
):
    monkeypatch.setattr(settings, "coach_reference_sha256", None)
    response = post_local(client, member, uploads[0])
    assert (
        response.status_code == 503
        and response.json()["code"] == "reference_configuration_required"
    )


def test_reference_job_result_roundtrip_and_ownership(
    client, member, uploads, temporal
):
    model, checksum, observed = temporal
    payload, factory = uploads
    response = post_local(client, member, payload)
    assert response.status_code == 202, response.text
    accepted = response.json()
    assert post_local(client, member, payload).json() == accepted
    assert post_local(client, member, payload, "pukulan_bandul").status_code == 409
    jobs = JobRepository(factory)
    claim = jobs.claim("temporal-test")
    assert claim.config["analyzerVersion"] == ANALYZER_VERSION
    assert claim.config["referenceModelChecksum"] == checksum and claim.references == []
    assert claim.config["featureVersion"] == FEATURE_VERSION
    result = analyze(
        "unused.mp4", "pukulan", "pukulan_depan", model, checksum, "unused.task", 60
    )
    assert jobs.complete(claim, result)
    evaluation = client.get(accepted["evaluationUrl"], headers=member)
    assert evaluation.status_code == 200, evaluation.text
    body = evaluation.json()
    assert body["analysisStatus"] == "reference_compared" and body["score"] is None
    assert (
        body["scoreReason"] == "correctness_not_validated"
        and body["method"] == "coach-reference-dtw"
    )
    assert body["coachComparison"]["movementId"] == "pukulan_depan"
    assert body["coachComparison"]["correctness"] is None
    assert len(body["coachComparison"]["frames"]) == 32
    assert "temporal_analysis_not_supported" not in body["unavailableReasons"]
    for secret in (
        "referenceSampleId",
        "sourceVideoSha256",
        "participantId",
        "isReferenceReplay",
    ):
        assert secret not in evaluation.text
    pose = client.get(accepted["statusUrl"] + "/pose", headers=member)
    assert pose.status_code == 200 and pose.json()["reason"] is None
    point = pose.json()["timeline"]["frames"][0]["landmarks"][0]
    assert point["x"] == pytest.approx(0.8 * 720 / 1280)
    assert point["y"] == 0.5
    other = client.post(
        "/api/v1/auth/sign-up",
        json={
            "fullName": "Other User",
            "identifier": "other@example.com",
            "password": "password123",
        },
    ).json()
    for tail in ("evaluation", "pose"):
        response = client.get(
            accepted["statusUrl"] + "/" + tail,
            headers={"Authorization": "Bearer " + other["accessToken"]},
        )
        assert response.status_code == 404
    detail = client.get(
        "/api/v1/member/history/" + accepted["sessionId"], headers=member
    )
    assert (
        detail.status_code == 200
        and detail.json()["evaluation"]["coachComparison"] == body["coachComparison"]
    )
    statistics = client.get("/api/v1/member/dashboard", headers=member).json()[
        "statistics"
    ]
    assert (
        statistics["completedSessionCount"] == 1
        and statistics["scoredSessionCount"] == 0
    )
    with factory() as db:
        owner = db.scalar(select(TrainingSession.user_id))
        assign_coach(db, owner, 1, "test-admin", "Temporal result access")
    login = client.post(
        "/api/v1/auth/sign-in",
        json={"identifier": "coach@example.com", "password": "password123"},
    ).json()
    coach_headers = {"Authorization": "Bearer " + login["accessToken"]}
    coach_path = "/api/v1/coach/sessions/" + accepted["sessionId"]
    coach_detail = client.get(coach_path, headers=coach_headers)
    assert (
        coach_detail.status_code == 200
        and coach_detail.json()["evaluation"]["coachComparison"]
        == body["coachComparison"]
    )
    assert client.get(coach_path + "/pose", headers=coach_headers).json()["timeline"][
        "frames"
    ]
    with factory() as db:
        assign_coach(db, owner, None, "test-admin", "Revoke temporal access")
    assert client.get(coach_path + "/pose", headers=coach_headers).status_code == 404


def test_complete_rejects_forged_target_or_model_version(
    client, member, uploads, temporal
):
    model, checksum, _ = temporal
    assert post_local(client, member, uploads[0]).status_code == 202
    jobs = JobRepository(uploads[1])
    claim = jobs.claim("fence-test")
    result = analyze(
        "unused", "pukulan", "pukulan_depan", model, checksum, "unused", 60
    )
    for mutate in (
        lambda r: r["model"].update(reference_version="0" * 64),
        lambda r: r["coach_comparison"].update(movementId="pukulan_bandul"),
        lambda r: r.update(score=80),
    ):
        altered = copy.deepcopy(result)
        mutate(altered)
        with pytest.raises(ValueError):
            jobs.complete(claim, altered)


def test_b2_reservation_freezes_analyzer_and_target_before_complete(
    client, member, remote, temporal, monkeypatch
):
    fake, _, factory = remote
    body = {**request_body(), "movementId": "pukulan_depan"}
    ticket = initiate(client, member, body).json()
    put(fake, ticket)
    # A deployment/config change must not reinterpret an in-flight upload.
    monkeypatch.setattr(settings, "analysis_mode", "static")
    monkeypatch.setattr(settings, "coach_reference_sha256", "f" * 64)
    response = finish(client, member, ticket)
    assert response.status_code == 202, response.text
    with factory() as db:
        config = db.scalar(select(AnalysisJob)).processing_config
    assert (
        config["referenceModelChecksum"] == temporal[1]
        and config["movementId"] == "pukulan_depan"
    )
    assert config["remoteUpload"] is True


def test_missing_corrupt_and_changed_artifact_fail_explicitly(temporal, tmp_path):
    _, checksum, _ = temporal
    assert load_reference(settings.coach_reference_model_path, checksum)
    with pytest.raises(ReferenceArtifactError, match="reference_model_unavailable"):
        load_reference(tmp_path / "missing.json", checksum)
    with pytest.raises(ReferenceArtifactError, match="reference_version_unavailable"):
        load_reference(settings.coach_reference_model_path, "f" * 64)
    bad = tmp_path / "bad.json"
    bad.write_text('{"value":NaN}')
    with pytest.raises(ReferenceArtifactError, match="reference_model_unavailable"):
        load_reference(bad, hashlib.sha256(bad.read_bytes()).hexdigest())


def test_child_checks_reference_and_pose_checksums(temporal, tmp_path, monkeypatch):
    path = tmp_path / "pose.task"
    path.write_bytes(b"fixture-model")
    config = dict(
        analyzerVersion=ANALYZER_VERSION,
        featureVersion=FEATURE_VERSION,
        modelPath=str(path),
        modelChecksum=hashlib.sha256(path.read_bytes()).hexdigest(),
        sampleFps=2,
        maxSeconds=60,
        method="coach-reference-dtw",
        movementId="pukulan_depan",
        referenceModelChecksum=temporal[1],
    )
    request = dict(config=config, references=[], video="unused", movement="pukulan")
    assert execute(request)["result"]["status"] == "reference_compared"
    config["referenceModelChecksum"] = "f" * 64
    assert execute(request)["error"] == "reference_version_unavailable"
    config["modelChecksum"] = "f" * 64
    assert execute(request)["error"] == "model_version_unavailable"


def test_timeline_does_not_invent_points_through_gaps(temporal):
    observed = copy.deepcopy(temporal[2])
    for row in observed["frames"]:
        if 0.4 < row["timeSeconds"] < 1.6:
            row["imageLandmarks"] = None
    output = timeline(observed)
    assert output["maximumInterpolationGapSeconds"] == 0.15
    assert not any(0.4 < f["timeSeconds"] < 1.6 for f in output["frames"])


def test_catalog_exposes_target_options_without_claiming_scoring(
    client, member, temporal
):
    response = client.get("/api/v1/member/record-config/pukulan", headers=member)
    assert response.status_code == 200
    body = response.json()
    assert body["movementIdRequired"] and len(body["movements"]) == 3
    catalog = client.get("/api/v1/member/training-modules", headers=member).json()
    assert all(
        m["capability"]["referenceComparisonAvailable"]
        and not m["capability"]["scoringAvailable"]
        for m in catalog["modules"]
    )


def test_timeline_bounds_long_video_payload_and_drops_unreliable_landmarks(temporal):
    observed = copy.deepcopy(temporal[2])
    row = observed["frames"][0]
    observed["frames"] = []
    for i in range(1001):
        frame = copy.deepcopy(row)
        frame.update(frameIndex=i, timeSeconds=i / 20)
        frame["imageLandmarks"][0][2] = 0.1
        observed["frames"].append(frame)
    output = timeline(observed)
    assert len(output["frames"]) <= 900
    assert output["frames"][0]["timeSeconds"] == 0
    assert all(p["index"] != 0 for f in output["frames"] for p in f["landmarks"])
