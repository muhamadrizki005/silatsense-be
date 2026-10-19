import cv2
import numpy as np
import pytest
from app.services.video import sampled_frames, InvalidVideo


def write_video(path, seconds=2):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (64, 64))
    assert writer.isOpened()
    for _ in range(seconds * 10):
        writer.write(np.zeros((64, 64, 3), dtype=np.uint8))
    writer.release()


def test_real_video_sampling_and_duration(tmp_path):
    path = tmp_path / "valid.mp4"
    write_video(path)
    frames = list(sampled_frames(path, 2, 60))
    assert [f[0] for f in frames] == [0, 5, 10, 15]
    assert frames[-1][1] == 1.5
    with pytest.raises(InvalidVideo):
        list(sampled_frames(path, 2, 1))


def test_disguised_video_rejected(tmp_path):
    path = tmp_path / "fake.mp4"
    path.write_bytes(b"not a video")
    with pytest.raises(InvalidVideo):
        list(sampled_frames(path, 2, 60))
