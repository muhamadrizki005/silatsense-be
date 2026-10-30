"""Offline elbow observations, not a technique classifier or correctness rubric."""

from collections import Counter

import numpy as np

from app.intelligence.features.biomechanics import angle

ELBOWS = {"left": (11, 13, 15), "right": (12, 14, 16)}
PHASES = {"neutral_start", "preparation", "execution", "recovery", "neutral_end"}
LITERATURE_URL = (
    "https://jurnal.unimed.ac.id/2012/index.php/so/article/download/51134/23708"
)


def spatial_angle(a, b, c):
    """Internal angle in model-estimated XYZ, never a measured 3D ground truth."""
    points = np.asarray([a, b, c], dtype=float)
    if points.shape != (3, 3) or not np.isfinite(points).all():
        return None
    u, v = points[0] - points[1], points[2] - points[1]
    denominator = np.linalg.norm(u) * np.linalg.norm(v)
    if denominator < 1e-8:
        return None
    return float(np.degrees(np.arccos(np.clip(np.dot(u, v) / denominator, -1, 1))))


def elbow_observation(image, world, side, width, height, visibility=0.5):
    """Image input is normalized x/y/z/visibility; world input is estimated XYZ."""
    if side not in ELBOWS or width <= 0 or height <= 0:
        raise ValueError("Invalid side or image dimensions")
    if not np.isfinite(visibility) or not 0 <= visibility <= 1:
        raise ValueError("Visibility must be between zero and one")
    result = dict(
        imageAngleDeg=None,
        estimatedWorldAngleDeg=None,
        disagreementDeg=None,
        minimumVisibility=None,
        reason=None,
    )
    if image is None:
        return {**result, "reason": "pose_unavailable"}
    image = np.asarray(image, dtype=float)
    if image.shape != (33, 4):
        return {**result, "reason": "invalid_landmarks"}
    indices = list(ELBOWS[side])
    points = image[indices]
    if not np.isfinite(points).all():
        return {**result, "reason": "nonfinite_landmarks"}
    result["minimumVisibility"] = float(points[:, 3].min())
    if (points[:, 3] < visibility).any():
        return {**result, "reason": "low_visibility"}
    if ((points[:, :2] < 0) | (points[:, :2] > 1)).any():
        return {**result, "reason": "joint_outside_image"}
    # Aspect correction is the same as the runtime pose extractor.
    corrected = points[:, :2].copy()
    corrected[:, 0] *= width / height
    result["imageAngleDeg"] = angle(*corrected)
    if result["imageAngleDeg"] is None:
        result["reason"] = "degenerate_projection"
    if world is not None:
        world = np.asarray(world, dtype=float)
        if world.shape == (33, 3):
            result["estimatedWorldAngleDeg"] = spatial_angle(*world[indices])
    if (
        result["imageAngleDeg"] is not None
        and result["estimatedWorldAngleDeg"] is not None
    ):
        result["disagreementDeg"] = abs(
            result["imageAngleDeg"] - result["estimatedWorldAngleDeg"]
        )
    return result


def validate_phases(segments, duration):
    if not isinstance(segments, list) or not segments:
        raise ValueError(
            "Annotations must be a nonempty list of manual phase intervals"
        )
    previous_end = 0.0
    for item in segments:
        if not isinstance(item, dict) or item.get("phase") not in PHASES:
            raise ValueError("Unknown phase")
        start, end = item.get("startSeconds"), item.get("endSeconds")
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not np.isfinite(value)
            for value in (start, end)
        ):
            raise ValueError("Phase times must be finite numbers")
        if not previous_end <= start < end <= duration:
            raise ValueError(
                "Phase intervals must be ordered, nonoverlapping and inside the video"
            )
        previous_end = end
    return segments


def phase_at(seconds, segments):
    for segment in segments or []:
        if segment["startSeconds"] <= seconds < segment["endSeconds"]:
            return segment["phase"]
    return None  # Never turn an unannotated transition into a ground-truth label.


def describe(values):
    values = [value for value in values if value is not None]
    return dict(
        sampleCount=len(values),
        minimum=min(values) if values else None,
        median=float(np.median(values)) if values else None,
        maximum=max(values) if values else None,
    )


def summarize(frames):
    if not frames:
        raise ValueError("No decoded video frames")
    output = {
        "observedFrameCount": len(frames),
        "sides": {},
        "assessmentStatus": "not_assessed",
        "correctness": None,
        "score": None,
        "measurementAccuracyValidated": False,
        "limitations": [
            "single_reference_video",
            "image_angles_are_projections",
            "estimated_3d_is_not_ground_truth",
            "front_view_rubric_not_validated",
            "detection_coverage_is_not_accuracy",
        ],
        "literature": {
            "url": LITERATURE_URL,
            "studySampleCount": 3,
            "measurementView": "sagittal",
            "thresholdsApplied": False,
            "reason": "Reported study measurements are not universal acceptance thresholds",
        },
    }
    for side in ELBOWS:
        measurements = [frame["elbows"][side] for frame in frames]
        output["sides"][side] = {
            "imageAngleDeg": describe([row["imageAngleDeg"] for row in measurements]),
            "estimatedWorldAngleDeg": describe(
                [row["estimatedWorldAngleDeg"] for row in measurements]
            ),
            "disagreementDeg": describe(
                [row["disagreementDeg"] for row in measurements]
            ),
            "unavailableReasons": dict(
                Counter(row["reason"] for row in measurements if row["reason"])
            ),
        }
    return output
