"""Presentation of measured features; scoring remains in the evaluator."""
import math

from app.schemas.results import Measurement, PoseData


FEATURES = [
    f"{side}_{joint}_angle" for side in ("left", "right")
    for joint in ("elbow", "shoulder", "hip", "knee")
] + [
    f"{side}_{name}_{axis}" for side in ("left", "right")
    for name in ("wrist_relative_to_shoulder", "ankle_relative_to_hip") for axis in ("x", "y")
] + ["torso_inclination", "shoulder_alignment", "hip_alignment", "stance_width_ratio"]


def metadata(feature):
    side = "left_" if feature.startswith("left_") else "right_" if feature.startswith("right_") else ""
    part = next((part for part in ("wrist", "ankle", "elbow", "shoulder", "hip", "knee", "stance")
                 if part in feature), "torso")
    unit = "shoulder_width" if "relative_to" in feature or feature == "stance_width_ratio" else "deg"
    return side + part, unit


def measurements(features, profile=None, compared=()):
    statistics = profile.get("feature_statistics", {}) if profile else {}
    items = []
    for name in FEATURES:
        value = features.get(name)
        stats = statistics.get(name, {})
        median, iqr = stats.get("median"), stats.get("iqr")
        assessed = name in compared and value is not None and iqr is not None and iqr > 1e-6
        delta = value - median if assessed else None
        part, unit = metadata(name)
        items.append(Measurement(
            feature=name, bodyPart=part, value=value, unit=unit,
            referenceMedian=median, referenceIqr=iqr, deviation=delta,
            assessment=("within_reference" if abs(delta) / iqr < 1 else "deviates") if assessed else "not_assessed",
            reason=None if assessed else "feature_unavailable" if value is None else "reference_not_comparable",
        ).model_dump())
    return items


def raw_pose(pose, rgb, index, seconds):
    height, width = rgb.shape[:2]
    landmarks = []
    # Extractor uses aspect-corrected x/z for geometry. Reverse that here,
    # before hip centering/scaling, for an overlay in image coordinates.
    for i, point in enumerate(pose.landmarks[:33]):
        x, y, z, visibility = map(float, point)
        if all(math.isfinite(v) for v in (x, y, z, visibility)) and 0 <= visibility <= 1:
            landmarks.append(dict(index=i, x=x * height / width, y=y,
                                  z=z * height / width, visibility=visibility))
    if not landmarks:
        return None
    return PoseData(frameIndex=index, timeSeconds=seconds, imageWidth=width,
                    imageHeight=height, landmarks=landmarks).model_dump()
