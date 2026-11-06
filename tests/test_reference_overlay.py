import copy

import cv2
import numpy as np
import pytest

from app.intelligence.reference_overlay import render
from app.intelligence.movement_video import file_hash


def inputs(tmp_path):
    video = tmp_path / "source.avi"
    writer = cv2.VideoWriter(
        str(video), cv2.VideoWriter_fourcc(*"MJPG"), 16, (256, 256)
    )
    assert writer.isOpened()
    for _ in range(32):
        writer.write(np.zeros((256, 256, 3), np.uint8))
    writer.release()
    points = [[0.4, 0.4, 1] for _ in range(33)]
    points[11], points[13], points[15] = [0.3, 0.3, 1], [0.4, 0.5, 1], [0.6, 0.5, 1]
    observations = {
        "sourceVideoSha256": file_hash(video),
        "video": {"decodedFrameCount": 32},
        "frames": [
            {"timeSeconds": i / 16, "imageLandmarks": copy.deepcopy(points)}
            for i in range(32)
        ],
    }
    comparison = {
        "status": "compared",
        "sourceVideoSha256": observations["sourceVideoSha256"],
        "frames": [
            {
                "timeSeconds": i / 16,
                "joints": {
                    "left_elbow": {"color": "red", "landmarkIndices": [11, 13, 15]},
                    "left_shoulder": {
                        "color": "green",
                        "landmarkIndices": [13, 11, 23],
                    },
                },
            }
            for i in range(32)
        ],
    }
    return video, observations, comparison


def test_real_mp4_encoder_preserves_worst_joint_color(tmp_path):
    video, observed, compared = inputs(tmp_path)
    output = tmp_path / "preview.mp4"
    assert render(video, observed, compared, output)["frameCount"] == 32
    cap = cv2.VideoCapture(str(output))
    ok, frame = cap.read()
    cap.release()
    assert ok
    # Forearm and the shared shoulder/elbow edge must remain red.
    for y, x in ((128, 128), (102, 90)):
        b, g, r = map(int, frame[y, x])
        assert r > 140 and r > g + 60 and r > b + 60


@pytest.mark.parametrize(
    "kind", ["hash", "missing_landmarks", "unassessable", "existing", "decode_count"]
)
def test_preview_failures_leave_no_partial_or_overwritten_output(tmp_path, kind):
    video, observed, compared = inputs(tmp_path)
    output = tmp_path / "preview.mp4"
    if kind == "hash":
        compared["sourceVideoSha256"] = "0" * 64
    elif kind == "missing_landmarks":
        for row in observed["frames"]:
            row["imageLandmarks"] = None
    elif kind == "unassessable":
        compared["status"] = "not_assessable"
    elif kind == "existing":
        output.write_bytes(b"existing user output")
    else:
        observed["video"]["decodedFrameCount"] += 1
    with pytest.raises(ValueError):
        render(video, observed, compared, output)
    if kind == "existing":
        assert output.read_bytes() == b"existing user output"
    else:
        assert not output.exists()
