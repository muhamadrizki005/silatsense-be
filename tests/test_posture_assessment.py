"""Synthetic geometry verifies policy, not accuracy on beginners or camera calibration."""

import copy
import json
from math import sin, pi
from types import SimpleNamespace

import pytest

from app.intelligence.movement_catalog import MOVEMENTS
from app.intelligence.posture_assessment import assess_posture
from app.intelligence.posture_rubric import RUBRICS
from app.schemas.temporal import PostureAssessment


def comparison(movement="kuda_kuda_samping", knee_delta=0):
    frames = []
    for i in range(32):
        action = max(0, sin(pi * (i - 5) / 20)) if 5 <= i <= 25 else 0
        formed = 10 <= i <= 20
        target = {
            "left_knee_deg": 100 if formed else 175,
            "right_knee_deg": 170,
            "left_elbow_deg": 80 + 90 * action,
            "right_elbow_deg": 90,
            "left_hip_deg": 170 - 70 * action,
            "right_hip_deg": 170,
            "stance_width_torso": 2.0 if formed else 0.6,
            "torso_inclination_deg": 8,
        }
        for limb in ("wrist", "ankle"):
            for side in ("left", "right"):
                target[f"{side}_{limb}_x_torso"] = action if side == "left" else 0.1
                target[f"{side}_{limb}_y_torso"] = -action if side == "left" else 1.0
        features = {
            name: dict(
                value=v,
                referenceValue=v,
                deviation=0,
                unit="deg" if name.endswith("_deg") else "torso_length_ratio",
                color=None,
                reason="tolerance_pending",
            )
            for name, v in target.items()
        }
        if formed:
            features["left_knee_deg"]["value"] += knee_delta
        frames.append(
            dict(
                timeSeconds=i * 0.1,
                referenceTimeSeconds=i * 0.1,
                features=features,
                joints={},
                phase=None,
            )
        )
    return dict(movementId=movement, status="compared", frames=frames)


@pytest.mark.parametrize("movement", MOVEMENTS)
def test_all_twelve_have_rubrics_and_score_matching_observable_action(movement):
    result = assess_posture(comparison(movement))
    PostureAssessment.model_validate(result)
    assert set(RUBRICS) == set(MOVEMENTS)
    assert result["status"] == "assessed" and result["points"] == 100
    assert all(
        a["points"] == 100 and a["correctionCode"] is None for a in result["aspects"]
    )


@pytest.mark.parametrize("movement", MOVEMENTS)
def test_all_twelve_reject_unobservable_pose_without_zero_scores(movement):
    c = comparison(movement)
    for frame in c["frames"]:
        for item in frame["features"].values():
            item["value"] = None
    result = assess_posture(c)
    assert result["status"] == "not_assessable" and result["points"] is None
    assert all(
        a["points"] is None and a["reason"] and a["correctionCode"] is None
        for a in result["aspects"]
    )


def test_formed_stance_ignores_neutral_setup_and_return():
    c = comparison(knee_delta=40)
    for i, f in enumerate(c["frames"]):
        if not 10 <= i <= 20:
            f["features"]["left_knee_deg"]["value"] = 40
    knee = assess_posture(c)["aspects"][0]
    assert knee["points"] == 85 and knee["correctionCode"] == "knee_bend_insufficient"


@pytest.mark.parametrize(
    "delta,points,code",
    [
        (0, 100, None),
        (20, 100, None),
        (20.1, 85, "knee_bend_insufficient"),
        (40, 85, "knee_bend_insufficient"),
        (-40, 85, "knee_bend_excessive"),
    ],
)
def test_knee_tiers_and_direction_are_measurement_based(delta, points, code):
    knee = assess_posture(comparison(knee_delta=delta))["aspects"][0]
    assert (knee["points"], knee["correctionCode"]) == (points, code)


def test_mixed_direction_loses_points_without_directional_correction():
    c = comparison()
    for i, f in enumerate(c["frames"]):
        if 10 <= i <= 20:
            f["features"]["left_knee_deg"]["value"] += 40 if i % 2 else -40
    knee = assess_posture(c)["aspects"][0]
    assert knee["points"] == 85 and knee["correctionCode"] is None


def test_missing_primary_aspect_suppresses_total_and_keeps_other_aspects():
    c = comparison()
    for f in c["frames"]:
        f["features"]["stance_width_torso"]["value"] = None
    result = assess_posture(c)
    assert result["status"] == "partial" and result["points"] is None
    assert [a["points"] for a in result["aspects"][:2]] == [100, 100]
    assert result["aspects"][2]["reason"] == "joint_not_observable"


def test_equal_weights_and_degree_ratio_tolerances_remain_separate():
    c = comparison(knee_delta=40)
    for f in c["frames"]:
        f["features"]["stance_width_torso"]["value"] -= 0.4
    result = assess_posture(c)
    assert [a["points"] for a in result["aspects"]] == [85, 100, 85]
    assert result["points"] == 90


@pytest.mark.parametrize("bad", [None, float("nan"), float("inf"), True, 999])
def test_invalid_angles_never_become_points(bad):
    c = comparison()
    for f in c["frames"]:
        f["features"]["left_knee_deg"]["value"] = bad
    assert assess_posture(c)["aspects"][0]["points"] is None


def test_wrong_units_and_insufficient_samples_are_not_assessed():
    c = comparison()
    for f in c["frames"]:
        f["features"]["stance_width_torso"]["unit"] = "deg"
    assert assess_posture(c)["aspects"][2]["points"] is None
    assert assess_posture({**c, "frames": c["frames"][:3]})["points"] is None


def test_mirrored_active_side_compares_to_same_anatomical_action():
    c = comparison("pukulan_bandul")
    for f in c["frames"]:
        for suffix in ("wrist_x_torso", "wrist_y_torso", "elbow_deg"):
            a, b = f["features"]["left_" + suffix], f["features"]["right_" + suffix]
            a["value"], b["value"] = b["value"], a["value"]
            if suffix.endswith("x_torso"):
                a["value"], b["value"] = -a["value"], -b["value"]
    assert assess_posture(c)["points"] == 100


def test_ambiguous_side_or_frozen_reference_alignment_is_not_fabricated():
    c = comparison("pukulan_bandul")
    for f in c["frames"]:
        for axis in ("x", "y"):
            f["features"][f"right_wrist_{axis}_torso"]["value"] = f["features"][
                f"left_wrist_{axis}_torso"
            ]["value"]
    assert assess_posture(c)["reason"] == "active_side_unclear"
    c = comparison("pukulan_bandul")
    for f in c["frames"]:
        f["referenceTimeSeconds"] = 1.0
    assert all(a["points"] is None for a in assess_posture(c)["aspects"])


def test_curve_shape_error_is_seen_even_if_endpoints_match():
    c = comparison("pukulan_melingkar")
    for i, f in enumerate(c["frames"]):
        if 7 <= i <= 13:
            f["features"]["left_wrist_x_torso"]["value"] += 0.9
    aspect = assess_posture(c)["aspects"][0]
    assert aspect["points"] < 100 and aspect["correctionCode"] is None


def test_body_ratio_end_position_has_direction_only_when_consistent():
    c = comparison("tangkisan_atas")
    for f in c["frames"]:
        f["features"]["left_wrist_y_torso"]["value"] += 0.4
    result = assess_posture(c)
    assert result["aspects"][1]["correctionCode"] == "wrist_position_too_low"


@pytest.mark.parametrize(
    "timeline",
    [
        {"imageWidth": 1280, "imageHeight": 720, "frames": []},
        {
            "imageWidth": 1280,
            "imageHeight": 720,
            "frames": [
                {
                    "timeSeconds": i * 0.1,
                    "landmarks": [
                        dict(index=k, x=0.5, y=0.5, visibility=1) for k in range(33)
                    ],
                }
                for i in range(32)
            ],
        },
    ],
)
def test_pose_gaps_and_degenerate_camera_projection_invalidate_affected_points(
    timeline,
):
    result = assess_posture(comparison(), timeline)
    assert result["points"] is None
    assert all(a["reason"] == "camera_or_pose_inadequate" for a in result["aspects"])


def test_oblique_projection_only_removes_aspects_that_need_visible_width():
    # Projected knees remain measurable, but shoulder baseline is collapsed.
    coordinates = {
        11: (0.499, 0.2),
        12: (0.501, 0.2),
        23: (0.45, 0.5),
        24: (0.55, 0.5),
        25: (0.4, 0.7),
        26: (0.6, 0.7),
        27: (0.3, 0.9),
        28: (0.7, 0.9),
    }
    timeline = dict(
        imageWidth=100,
        imageHeight=100,
        frames=[
            dict(
                timeSeconds=i * 0.1,
                landmarks=[
                    dict(index=k, x=x, y=y, visibility=1)
                    for k, (x, y) in coordinates.items()
                ],
            )
            for i in range(32)
        ],
    )
    result = assess_posture(comparison(), timeline)
    assert result["points"] is None and result["status"] == "partial"
    assert [a["points"] for a in result["aspects"]] == [100, 100, None]
    assert result["aspects"][2]["reason"] == "camera_or_pose_inadequate"


def test_read_projection_is_pure_and_does_not_trust_cached_assessment():
    from app.models.entities import now
    from app.services.results import evaluation_out

    c = comparison()
    c.update(
        experimental=True,
        correctness=None,
        score=None,
        qualityAssessmentValidated=False,
        toleranceStatus="experimental",
        features={},
        alignmentDistance=0,
        semanticPhasesAvailable=False,
    )
    c["postureAssessment"] = dict(
        status="assessed", points=1, maxPoints=100, reason=None, aspects=[]
    )
    data = dict(
        analysis={
            "method": "coach-reference-dtw",
            "frames_processed": 32,
            "valid_pose_frames": 32,
        },
        model={"feature_version": "movement-image-features-v1"},
        issues=[],
        pose_status="detected",
        coach_comparison=c,
    )
    before = copy.deepcopy(data)
    row = SimpleNamespace(
        result_json=data,
        id=1,
        movement="kuda_kuda",
        created_at=now(),
        status="reference_compared",
        score=None,
        matched_variant="kuda_kuda_samping",
        analyzer_version="coach-reference-dtw-v1",
        reference_version="a" * 64,
    )
    body = evaluation_out(SimpleNamespace(id=1), row).model_dump(mode="json")
    assert body["coachComparison"]["postureAssessment"]["points"] == 100
    assert body["score"] is None and body["coachComparison"]["score"] is None
    assert data == before
    json.dumps(body, allow_nan=False)


def test_legacy_backfill_on_authenticated_evaluation_history_and_coach_reads(
    client, member, uploads, temporal
):
    from sqlalchemy import select
    from app.models.entities import EvaluationSession, TrainingSession
    from app.repositories.jobs import JobRepository
    from app.services.assignments import assign_coach
    from app.services.coach_analysis import analyze
    from test_coach_analysis_api import post_local

    model, checksum, _ = temporal
    accepted = post_local(client, member, uploads[0]).json()
    jobs = JobRepository(uploads[1])
    claim = jobs.claim("posture-fixture-only")
    result = analyze(
        "fixture", "pukulan", "pukulan_depan", model, checksum, "fixture", 60
    )
    assert jobs.complete(claim, result)
    with uploads[1]() as db:
        row = db.scalar(select(EvaluationSession))
        data = copy.deepcopy(row.result_json)
        # Simulate an old evaluation containing sufficient paired features, no timeline.
        data["coach_comparison"]["frames"] = comparison("pukulan_depan")["frames"]
        data["coach_comparison"].pop("postureAssessment", None)
        data.pop("pose_timeline", None)
        row.result_json = data
        owner = db.scalar(select(TrainingSession.user_id))
        db.commit()
        assign_coach(db, owner, 1, "test-admin", "Read-time assessment access")
    before = copy.deepcopy(data)
    evaluation = client.get(accepted["evaluationUrl"], headers=member).json()
    expected = evaluation["coachComparison"]["postureAssessment"]
    assert expected["points"] == 100 and evaluation["score"] is None
    history = client.get(
        "/api/v1/member/history/" + accepted["sessionId"], headers=member
    ).json()
    assert history["evaluation"]["coachComparison"]["postureAssessment"] == expected
    login = client.post(
        "/api/v1/auth/sign-in",
        json={"identifier": "coach@example.com", "password": "password123"},
    ).json()
    coach = client.get(
        "/api/v1/coach/sessions/" + accepted["sessionId"],
        headers={"Authorization": "Bearer " + login["accessToken"]},
    ).json()
    assert coach["evaluation"]["coachComparison"]["postureAssessment"] == expected
    with uploads[1]() as db:
        assert db.scalar(select(EvaluationSession)).result_json == before


# Existing fixtures only use disposable SQLite/media and a synthetic model.
from test_coach_analysis_api import temporal  # noqa: E402,F401
from test_sessions_jobs import uploads  # noqa: E402,F401
