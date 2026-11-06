import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from app.intelligence.punch_diagnostics import (
    elbow_observation,
    phase_at,
    spatial_angle,
    summarize,
    validate_phases,
)
from scripts.analyze_punch_reference import analyze, detect, json_landmarks


def landmarks():
    image = np.tile([0.5, 0.5, 0.0, 1.0], (33, 1))
    image[11] = [0.2, 0.4, 0, 1]
    image[13] = [0.4, 0.4, 0, 1]
    image[15] = [0.6, 0.6, 0, 1]
    world = np.zeros((33, 3))
    world[11], world[13], world[15] = [0, 0, 0], [1, 0, 0], [1, 1, 0]
    return image, world


def test_image_angle_uses_aspect_correction_and_world_uses_three_dimensions():
    image, world = landmarks()
    result = elbow_observation(image, world, "left", 1280, 640)
    assert result["imageAngleDeg"] == pytest.approx(153.4349488)
    assert result["estimatedWorldAngleDeg"] == pytest.approx(90)
    assert result["disagreementDeg"] == pytest.approx(63.4349488)
    assert result["reason"] is None
    assert spatial_angle([0, 0, 0], [0, 0, 1], [0, 1, 1]) == pytest.approx(90)


@pytest.mark.parametrize(
    "fault,reason",
    [
        ("missing", "pose_unavailable"),
        ("shape", "invalid_landmarks"),
        ("visibility", "low_visibility"),
        ("nan", "nonfinite_landmarks"),
        ("outside", "joint_outside_image"),
    ],
)
def test_unobservable_points_do_not_become_angles_or_correctness(fault, reason):
    image, world = landmarks()
    if fault == "missing":
        image = None
    elif fault == "shape":
        image = image[:32]
    elif fault == "visibility":
        image[13, 3] = 0.1
    elif fault == "nan":
        image[13, 0] = np.nan
    else:
        image[13, 0] = 1.2
    result = elbow_observation(image, world, "left", 1280, 720)
    assert result["imageAngleDeg"] is None
    assert result["estimatedWorldAngleDeg"] is None
    assert result["reason"] == reason


def test_collapsed_projection_can_still_record_estimated_world_angle():
    image, world = landmarks()
    image[13, :2] = image[11, :2]
    result = elbow_observation(image, world, "left", 1280, 720)
    assert result["reason"] == "degenerate_projection"
    assert result["imageAngleDeg"] is result["disagreementDeg"] is None
    assert result["estimatedWorldAngleDeg"] == pytest.approx(90)


def test_degenerate_or_absent_world_data_remains_null():
    image, _ = landmarks()
    assert spatial_angle([0, 0, 0], [0, 0, 0], [1, 1, 1]) is None
    assert spatial_angle([np.nan, 0, 0], [1, 0, 0], [1, 1, 0]) is None
    result = elbow_observation(image, None, "left", 1280, 720)
    assert result["imageAngleDeg"] is not None
    assert result["estimatedWorldAngleDeg"] is None


@pytest.mark.parametrize(
    "segments",
    [
        [],
        [{"phase": "made_up", "startSeconds": 0, "endSeconds": 1}],
        [{"phase": "execution", "startSeconds": 2, "endSeconds": 1}],
        [{"phase": "execution", "startSeconds": 0, "endSeconds": 5}],
        [{"phase": "execution", "startSeconds": 0, "endSeconds": float("nan")}],
        [
            {"phase": "execution", "startSeconds": 0, "endSeconds": 2},
            {"phase": "recovery", "startSeconds": 1, "endSeconds": 3},
        ],
    ],
)
def test_invalid_manual_phases_rejected(segments):
    with pytest.raises(ValueError):
        validate_phases(segments, 4)


def test_phase_boundaries_are_explicit_and_unannotated_frames_stay_unlabeled():
    segments = validate_phases(
        [
            {"phase": "neutral_start", "startSeconds": 0, "endSeconds": 1},
            {"phase": "execution", "startSeconds": 1, "endSeconds": 3},
        ],
        4,
    )
    assert phase_at(0, segments) == "neutral_start"
    assert phase_at(1, segments) == "execution"
    assert phase_at(3, segments) is None
    assert phase_at(1, None) is None


def test_perfect_detection_or_angle_agreement_is_not_a_validated_assessment():
    observation = dict(
        imageAngleDeg=90.0,
        estimatedWorldAngleDeg=90.0,
        disagreementDeg=0.0,
        minimumVisibility=1.0,
        reason=None,
    )
    frames = [{"elbows": {"left": observation, "right": observation}} for _ in range(3)]
    result = summarize(frames)
    assert result["observedFrameCount"] == 3
    assert result["sides"]["left"]["imageAngleDeg"]["sampleCount"] == 3
    assert result["assessmentStatus"] == "not_assessed"
    assert result["score"] is result["correctness"] is None
    assert not result["measurementAccuracyValidated"]
    assert not result["literature"]["thresholdsApplied"]


def test_missing_observations_have_zero_samples_and_null_statistics():
    observation = elbow_observation(None, None, "left", 1280, 720)
    result = summarize([{"elbows": {"left": observation, "right": observation}}])
    statistics = result["sides"]["left"]["imageAngleDeg"]
    assert statistics == dict(sampleCount=0, minimum=None, median=None, maximum=None)
    with pytest.raises(ValueError):
        summarize([])


def test_detector_refuses_multiple_people_and_json_has_no_nan():
    response = SimpleNamespace(pose_landmarks=[[], []], pose_world_landmarks=[])
    extractor = SimpleNamespace(
        detector=SimpleNamespace(detect=lambda value: response),
        mp=SimpleNamespace(
            Image=lambda **kwargs: kwargs, ImageFormat=SimpleNamespace(SRGB="rgb")
        ),
    )
    assert detect(extractor, np.zeros((2, 2, 3), dtype=np.uint8)) == (None, None, 2)
    assert json_landmarks(np.array([[np.nan, 1.0]])) == [[None, 1.0]]
    assert json.dumps(json_landmarks(np.array([[np.nan, 1.0]])), allow_nan=False)


def test_cli_rejects_output_overwrite_before_loading_model(tmp_path):
    video, model = tmp_path / "video.mp4", tmp_path / "model.task"
    video.touch()
    model.touch()
    with pytest.raises(ValueError, match="output sudah ada"):
        analyze(video, model, tmp_path)


@pytest.mark.skipif(
    not Path("artifacts/pose/pose_landmarker_lite.task").is_file(),
    reason="Private local pose model not installed",
)
def test_real_blank_video_is_observed_without_inventing_pose_or_phases(tmp_path):
    import cv2

    video = tmp_path / "blank.mp4"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 10, (64, 64))
    assert writer.isOpened()
    for _ in range(10):
        writer.write(np.zeros((64, 64, 3), dtype=np.uint8))
    writer.release()
    result = analyze(
        video, Path("artifacts/pose/pose_landmarker_lite.task"), tmp_path / "out"
    )
    assert len(result["frames"]) == 10
    assert all(row["phase"] is None for row in result["frames"])
    assert result["summary"]["sides"]["left"]["imageAngleDeg"]["sampleCount"] == 0
    assert (tmp_path / "out/observations.json").is_file()
    assert result["summary"]["score"] is None
