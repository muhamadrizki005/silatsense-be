"""Validate privately extracted temporal samples and prevent split leakage."""

from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import re

from app.intelligence.movement_catalog import MOVEMENTS
from app.intelligence.movement_features import FEATURE_NAMES, FEATURE_VERSION
from app.intelligence.punch_dataset import private_file

FIELDS = (
    "sampleId",
    "participantId",
    "recordingId",
    "split",
    "movementId",
    "labelSource",
    "qualityLabel",
    "observationsPath",
)
SPLITS = {"train", "validation", "test"}


def validate_report(report):
    if (
        report.get("schemaVersion") != 1
        or report.get("featureVersion") != FEATURE_VERSION
    ):
        raise ValueError("Incompatible movement observations")
    duration = report["video"]["durationSeconds"]
    if (
        isinstance(duration, bool)
        or not isinstance(duration, (int, float))
        or not math.isfinite(duration)
        or duration <= 0
    ):
        raise ValueError("Invalid duration")
    if report.get("cameraView") != "front_fixed_as_input_assumption":
        raise ValueError("Only the agreed fixed front camera is supported")
    for name in ("sourceVideoSha256", "poseModelSha256"):
        if not isinstance(report.get(name), str) or not re.fullmatch(
            r"[0-9a-f]{64}", report[name]
        ):
            raise ValueError("Invalid video/model fingerprint")
    signature = report.get("extractionSignature", {})
    if (
        signature.get("poseModelSha256") != report["poseModelSha256"]
        or signature.get("featureVersion") != FEATURE_VERSION
        or signature.get("cameraView") != report["cameraView"]
        or signature.get("maximumImageDimension") != 1280
        or set(signature.get("versions", {}))
        != {"numpy", "mediapipe", "opencv-contrib-python"}
    ):
        raise ValueError("Invalid extraction signature")
    for key, minimum, maximum in (
        ("sampleFpsRequested", 0, 60),
        ("visibilityThreshold", 0, 1),
    ):
        value = signature.get(key)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not minimum <= value <= maximum
            or (key == "sampleFpsRequested" and value == 0)
        ):
            raise ValueError("Invalid extraction configuration")
    previous = -1
    for row in report["frames"]:
        t = row["timeSeconds"]
        if (
            isinstance(t, bool)
            or not isinstance(t, (int, float))
            or not math.isfinite(t)
            or not 0 <= t < duration
            or t <= previous
        ):
            raise ValueError(
                "Frame times must be finite, increasing, and inside duration"
            )
        if set(row["features"]) != set(FEATURE_NAMES):
            raise ValueError("Feature schema mismatch")
        if row.get("frameIndex") is not None:
            index = row["frameIndex"]
            if isinstance(index, bool) or not isinstance(index, int) or index < 0:
                raise ValueError("Invalid frame index")
        for name, value in row["features"].items():
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise ValueError("Features must be finite or null")
            if value is not None and name.endswith("_deg") and not 0 <= value <= 180:
                raise ValueError("Invalid geometric angle")
            if value is None and not row.get("unavailableReasons", {}).get(name):
                raise ValueError("Missing features require a reason")
        previous = t
    if not report["frames"]:
        raise ValueError("Empty observation sequence")
    return report


def prepare(manifest, data_root):
    root = Path(data_root).resolve()
    with Path(manifest).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise ValueError("Use docs/templates/movement-dataset.csv header")
        entries = list(reader)
    if not entries:
        raise ValueError("Empty manifest; real training data is required")
    samples, identifiers, videos, groups, signatures = [], set(), set(), {}, set()
    for entry in entries:
        if None in entry or any(
            value is None or not value.strip() for value in entry.values()
        ):
            raise ValueError("Missing or malformed manifest fields")
        entry = {key: value.strip() for key, value in entry.items()}
        if entry["sampleId"] in identifiers:
            raise ValueError("Duplicate sampleId")
        identifiers.add(entry["sampleId"])
        if entry["movementId"] not in MOVEMENTS or entry["split"] not in SPLITS:
            raise ValueError("Unknown movementId or split")
        if entry["labelSource"] not in {"coach_review", "user_confirmed_reference"}:
            raise ValueError("Movement label provenance is required")
        if entry["qualityLabel"] not in {"unlabeled", "correct", "needs_correction"}:
            raise ValueError("Unknown quality label")
        if (
            entry["qualityLabel"] != "unlabeled"
            and entry["labelSource"] != "coach_review"
        ):
            raise ValueError(
                "Quality labels require coach review; naming is not grading"
            )
        content = private_file(root, entry["observationsPath"]).read_bytes()
        report = validate_report(json.loads(content))
        video = report["sourceVideoSha256"]
        if video in videos:
            raise ValueError("Duplicate video content")
        videos.add(video)
        for key, value in (
            ("participantId", entry["participantId"]),
            ("recordingId", entry["recordingId"]),
            ("video", video),
        ):
            group = (key, value)
            if group in groups and groups[group] != entry["split"]:
                raise ValueError("Cross-split data leakage: " + key)
            groups[group] = entry["split"]
        signature = report["extractionSignature"]
        if signature.get("poseModelSha256") != report["poseModelSha256"]:
            raise ValueError("Pose model fingerprint mismatch")
        signatures.add(json.dumps(signature, sort_keys=True))
        samples.append(
            {
                **{k: v for k, v in entry.items() if k != "observationsPath"},
                "observationsSha256": hashlib.sha256(content).hexdigest(),
                "observations": report,
            }
        )
    if len(signatures) != 1:
        raise ValueError(
            "Use identical model, dependencies and extraction configuration"
        )
    counts = Counter(s["split"] for s in samples)
    return {
        "schemaVersion": 1,
        "datasetType": "movement-recognition-v1",
        "featureVersion": FEATURE_VERSION,
        "extractionSignature": json.loads(next(iter(signatures))),
        "sampleCount": len(samples),
        "splitCounts": dict(counts),
        "movementCounts": dict(Counter(s["movementId"] for s in samples)),
        "trainedModelCreated": False,
        "qualityAssessmentValidated": False,
        "samples": samples,
    }
