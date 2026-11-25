"""Optional local regressions. Private observations/videos NEVER become Git fixtures.

Public CI still tests every movement using synthetic, observable geometry.
"""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from app.intelligence.movement_catalog import MOVEMENTS
from app.intelligence.posture_assessment import assess_posture
from app.schemas.temporal import PostureAssessment


@pytest.mark.parametrize("movement", MOVEMENTS)
def test_available_mapped_demo_replays(movement):
    path = Path(".cache/coach-reference-20261030") / f"{movement}-replay.json"
    if not path.is_file():
        pytest.skip("Private mapped Coach demo comparison not present")
    result = assess_posture(json.loads(path.read_text()))
    PostureAssessment.model_validate(result)
    assert result["aspects"]
    # Matching visible geometry is 100; ambiguity must stay null, never dummy points.
    assert all(
        a["points"] == 100 or a["points"] is None and a["reason"]
        for a in result["aspects"]
    )


@pytest.mark.parametrize("movement", MOVEMENTS)
def test_available_held_out_coach_frames_and_unclear_pose(movement):
    root = Path(".cache/coach-api-native-smoke-20261123-v3")
    path = root / f"{movement}-evaluation.json"
    if not path.is_file():
        pytest.skip("Private held-out Coach comparison not present")
    c = json.loads(path.read_text())["coachComparison"]
    timeline = json.loads((root / f"{movement}-pose.json").read_text())["timeline"]
    result = assess_posture(c, timeline)
    PostureAssessment.model_validate(result)
    for a in result["aspects"]:
        assert a["reason"] if a["points"] is None else 0 <= a["points"] <= 100
    result = assess_posture(c, {**timeline, "frames": []})
    assert result["points"] is None
    assert all(a["points"] is None for a in result["aspects"])


@pytest.mark.parametrize(
    "filename,points,correction",
    [
        ("orang 7.mp4", 100, None),
        ("orang 1(2).mp4", 85, "knee_bend_insufficient"),
    ],
)
def test_side_stance_knee_real_video_regression(filename, points, correction):
    root = Path(".cache/coach-baseline-20261123")
    source = Path("C:/Datasets/SilatSense") / filename
    if not source.is_file() or not (root / "dataset.json").is_file():
        pytest.skip("Private video/extracted observations are not present")
    from app.intelligence.coach_reference import compare
    from app.services.coach_analysis import timeline
    import cv2

    dataset = json.loads((root / "dataset.json").read_text())
    checksum = hashlib.sha256(source.read_bytes()).hexdigest()
    report = next(
        s["observations"]
        for s in dataset["samples"]
        if s["observations"]["sourceVideoSha256"] == checksum
    )
    report = copy.deepcopy(report)
    # Older offline reports lacked dimensions. Recover only metadata, no re-extraction.
    video = cv2.VideoCapture(str(source))
    try:
        report["video"].update(
            imageWidth=int(video.get(cv2.CAP_PROP_FRAME_WIDTH)),
            imageHeight=int(video.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        )
    finally:
        video.release()
    model = json.loads((root / "reference-model.json").read_text())
    result = assess_posture(
        compare(model, report, "kuda_kuda_samping"), timeline(report)
    )
    knee = next(a for a in result["aspects"] if a["id"] == "bent_knee")
    assert (knee["points"], knee["correctionCode"]) == (points, correction)
