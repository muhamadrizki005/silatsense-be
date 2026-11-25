"""Worker-only adapter from private temporal artifacts to stored/public results."""

import hashlib
import json
import math
from pathlib import Path

from app.intelligence.coach_contracts import ANALYZER_VERSION, FEATURE_VERSION, METHOD
from app.schemas.temporal import CoachComparison, PoseTimeline


class ReferenceArtifactError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def load_reference(path, checksum):
    from app.intelligence.coach_reference import _array, MODEL_TYPE
    from app.intelligence.movement_catalog import MOVEMENTS
    from app.intelligence.movement_features import FAMILY_FEATURES, FEATURE_UNITS
    from app.intelligence.movement_training import BINS
    from app.intelligence.reference_alignment import WARP_RADIUS

    try:
        raw = Path(path).read_bytes()
    except OSError:
        raise ReferenceArtifactError("reference_model_unavailable") from None
    if not checksum or hashlib.sha256(raw).hexdigest() != checksum:
        raise ReferenceArtifactError("reference_version_unavailable")
    try:
        model = json.loads(raw)
        if (
            model["schemaVersion"] != 1
            or model["modelType"] != MODEL_TYPE
            or model["featureVersion"] != FEATURE_VERSION
            or model["temporalBins"] != BINS
            or model["warpRadius"] != WARP_RADIUS
            or not model["profiles"]
        ):
            raise ValueError("Incompatible artifact")
        for movement, profile in model["profiles"].items():
            names = list(FAMILY_FEATURES[MOVEMENTS[movement][0]])
            if (
                profile["featureNames"] != names
                or not profile["templates"]
                or set(profile["tolerances"]) != set(names)
            ):
                raise ValueError("Invalid profile")
            for template in profile["templates"]:
                if _array(template["sequence"]).shape != (BINS, len(names)):
                    raise ValueError("Invalid sequence")
            for name, threshold in profile["tolerances"].items():
                if threshold is not None and (
                    threshold["unit"] != FEATURE_UNITS[name]
                    or not 0 < threshold["yellowAbove"] < threshold["redAbove"]
                    or not all(
                        type(threshold[k]) in (int, float)
                        and math.isfinite(threshold[k])
                        for k in ("yellowAbove", "redAbove")
                    )
                ):
                    raise ValueError("Invalid tolerances")
        # Reject nonstandard JSON numbers anywhere, including metadata.
        json.dumps(model, allow_nan=False)
        signature = model["extractionSignature"]
        if (
            signature["featureVersion"] != FEATURE_VERSION
            or signature["maximumImageDimension"] != 1280
            or signature["cameraView"] != "front_fixed_as_input_assumption"
            or set(signature["versions"])
            != {"numpy", "mediapipe", "opencv-contrib-python"}
            or not 0 < signature["sampleFpsRequested"] <= 60
            or not 0 <= signature["visibilityThreshold"] <= 1
        ):
            raise ValueError("Invalid extraction settings")
        return model
    except (ValueError, TypeError, KeyError, IndexError, OverflowError):
        raise ReferenceArtifactError("reference_model_unavailable") from None


def timeline(report):
    """Bounded actual observations, never fabricated/interpolated landmarks."""
    rows = report["frames"]
    width, height = report["video"]["imageWidth"], report["video"]["imageHeight"]
    frames = []
    stride = max(1, math.ceil(len(rows) / 900))
    for row in rows[::stride]:
        if row.get("imageLandmarks") is None:
            continue
        points = []
        for index, (x, y, visibility) in enumerate(row["imageLandmarks"]):
            if (
                None not in (x, y, visibility)
                and all(math.isfinite(v) for v in (x, y, visibility))
                and 0 <= x * height / width <= 1
                and 0 <= y <= 1
                and report["extractionSignature"]["visibilityThreshold"]
                <= visibility
                <= 1
            ):
                points.append(
                    dict(index=index, x=x * height / width, y=y, visibility=visibility)
                )
        if points:
            frames.append(
                dict(
                    frameIndex=row["frameIndex"],
                    timeSeconds=row["timeSeconds"],
                    landmarks=points,
                )
            )
    return PoseTimeline(
        imageWidth=width, imageHeight=height, frames=frames
    ).model_dump()


def analyze(
    video, category, movement_id, model, checksum, pose_model_path, max_seconds
):
    from app.intelligence.coach_reference import compare
    from app.intelligence.movement_catalog import MOVEMENTS
    from app.intelligence.movement_video import extract_video

    if movement_id not in MOVEMENTS or MOVEMENTS[movement_id][0] != category:
        raise ValueError("Invalid target movement")
    signature = model["extractionSignature"]
    report = extract_video(
        video,
        pose_model_path,
        sample_fps=signature["sampleFpsRequested"],
        visibility=signature["visibilityThreshold"],
        max_seconds=max_seconds,
        include_landmarks=True,
    )
    # compare rejects model/extraction/dependency mismatches; never silently downgrade.
    comparison = compare(model, report, movement_id)
    public = {k: v for k, v in comparison.items() if k in CoachComparison.model_fields}
    public = CoachComparison.model_validate(public).model_dump()
    detected = sum(bool(row.get("imageLandmarks")) for row in report["frames"])
    status = (
        "reference_compared"
        if public["status"] == "compared"
        else "insufficient_features"
        if detected
        else "insufficient_pose"
    )
    return {
        "movement": category,
        "matched_variant": movement_id,
        "reference_profile_id": None,
        "score": None,
        "status": status,
        "pose_status": "detected" if detected else "not_detected",
        "analysis": {
            "frames_processed": len(report["frames"]),
            "valid_pose_frames": detected,
            "key_frame": None,
            "key_frame_time": None,
            "method": METHOD,
            "features_compared": len(public["features"])
            if public["status"] == "compared"
            else None,
        },
        "model": {
            "analyzer_version": ANALYZER_VERSION,
            "feature_version": FEATURE_VERSION,
            "reference_version": checksum,
        },
        "pose": None,
        "measurements": [],
        "issues": [],
        "coach_comparison": public,
        "pose_timeline": timeline(report),
    }
