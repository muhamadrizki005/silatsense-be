"""Native offline extraction; no API, database, storage retention or worker changes."""

from collections import Counter
import hashlib
import importlib.metadata
import math
from pathlib import Path

from app.intelligence.movement_features import FEATURE_VERSION, extract_features


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_video(video, model, sample_fps=15.0, visibility=0.5, max_seconds=60.0):
    import cv2
    import numpy as np
    from app.intelligence.pose.mediapipe_extractor import MediaPipePoseExtractor

    if (
        not all(math.isfinite(v) for v in (sample_fps, visibility, max_seconds))
        or not 0 < sample_fps <= 60
        or not 0 <= visibility <= 1
        or max_seconds <= 0
    ):
        raise ValueError("Invalid extraction settings")
    if not Path(video).is_file() or not Path(model).is_file():
        raise ValueError("Video or pose model is missing")
    capture, extractor = cv2.VideoCapture(str(video)), None
    try:
        capture.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)
        fps, count = (
            capture.get(cv2.CAP_PROP_FPS),
            capture.get(cv2.CAP_PROP_FRAME_COUNT),
        )
        if (
            not capture.isOpened()
            or not math.isfinite(fps)
            or not 0 < fps <= 240
            or not math.isfinite(count)
            or count < 1
        ):
            raise ValueError("Unreadable video or invalid metadata")
        duration = count / fps
        if duration > max_seconds:
            raise ValueError("Video exceeds maximum duration")
        stride = max(1, round(fps / sample_fps))
        extractor = MediaPipePoseExtractor(str(model))
        frames, index = [], 0
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if index / fps >= max_seconds:
                raise ValueError("Decoded video exceeds duration limit")
            if index % stride == 0:
                height, width = frame.shape[:2]
                scale = min(1, 1280 / max(width, height))
                if scale < 1:
                    frame = cv2.resize(
                        frame, (round(width * scale), round(height * scale))
                    )
                pose = extractor.extract(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                landmarks = pose.landmarks if pose is not None else None
                if landmarks is not None:
                    # The extractor already corrects aspect ratio. Reject joints outside
                    # the image and unreliable detections before computing any feature.
                    h, w = frame.shape[:2]
                    landmarks = landmarks.copy()
                    outside = (
                        (landmarks[:, 0] < 0)
                        | (landmarks[:, 0] > w / h)
                        | (landmarks[:, 1] < 0)
                        | (landmarks[:, 1] > 1)
                    )
                    landmarks[outside, 3] = np.nan
                observed = extract_features(landmarks, visibility)
                frames.append(
                    {
                        "timeSeconds": index / fps,
                        "frameIndex": index,
                        "features": observed["values"],
                        "unavailableReasons": observed["unavailableReasons"],
                    }
                )
            index += 1
        if index < int(count) - 1 or not frames:
            raise ValueError("Video decoding incomplete")
        signature = {
            "featureVersion": FEATURE_VERSION,
            "poseModelSha256": file_hash(model),
            "sampleFpsRequested": sample_fps,
            "visibilityThreshold": visibility,
            "maximumImageDimension": 1280,
            "cameraView": "front_fixed_as_input_assumption",
            "versions": {
                name: importlib.metadata.version(name)
                for name in ("numpy", "mediapipe", "opencv-contrib-python")
            },
        }
        return {
            "schemaVersion": 1,
            "featureVersion": FEATURE_VERSION,
            "sourceVideoSha256": file_hash(video),
            "poseModelSha256": signature["poseModelSha256"],
            "cameraView": signature["cameraView"],
            "extractionSignature": signature,
            "video": {
                "durationSeconds": duration,
                "fps": fps,
                "decodedFrameCount": index,
                "samplingStride": stride,
            },
            "coverage": {
                name: sum(row["features"][name] is not None for row in frames)
                / len(frames)
                for name in frames[0]["features"]
            },
            "unavailableReasonCounts": dict(
                Counter(
                    reason
                    for row in frames
                    for reason in row["unavailableReasons"].values()
                    if reason
                )
            ),
            "qualityAssessment": None,
            "frames": frames,
        }
    finally:
        capture.release()
        if extractor is not None:
            extractor.close()
