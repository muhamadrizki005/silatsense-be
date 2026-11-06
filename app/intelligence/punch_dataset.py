"""Prepare temporal experiment inputs; deliberately does not train or grade anyone."""

from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import re

from app.intelligence.punch_diagnostics import phase_at, validate_phases

FIELDS = (
    "sampleId",
    "participantId",
    "recordingId",
    "split",
    "label",
    "labelSource",
    "cameraView",
    "observationsPath",
    "annotationsPath",
)
SPLITS = {"train", "validation", "test"}
LABELS = {"correct", "needs_correction", "unlabeled"}
SOURCES = {"coach_review", "user_reports_coach_demo", "unlabeled"}


def private_file(root, relative):
    if not relative or Path(relative).is_absolute():
        raise ValueError("Dataset paths must be relative to data-root")
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("Dataset file missing or outside data-root")
    return path


def sequence(report, phases):
    rows, previous, previous_frame = [], -1.0, -1
    duration = report["video"]["durationSeconds"]
    if (
        isinstance(duration, bool)
        or not isinstance(duration, (int, float))
        or not math.isfinite(duration)
        or duration <= 0
    ):
        raise ValueError("Invalid video duration")
    for row in report["frames"]:
        seconds, index = row["timeSeconds"], row["frameIndex"]
        if (
            isinstance(seconds, bool)
            or not isinstance(seconds, (int, float))
            or not math.isfinite(seconds)
            or not previous < seconds < duration
            or not isinstance(index, int)
            or isinstance(index, bool)
            or index <= previous_frame
        ):
            raise ValueError(
                "Frames must have finite, ordered times and increasing indices"
            )
        values = {}
        for side in ("left", "right"):
            for field in ("imageAngleDeg", "estimatedWorldAngleDeg"):
                value = row["elbows"][side][field]
                if value is not None and (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    or not 0 <= value <= 180
                ):
                    raise ValueError(
                        "Angle must be null or finite within its geometric range"
                    )
                values[f"{side}.{field}"] = value
        rows.append(
            dict(
                frameIndex=index,
                timeSeconds=seconds,
                phase=phase_at(seconds, phases),
                features=values,
            )
        )
        previous, previous_frame = seconds, index
    if not rows:
        raise ValueError("An empty sequence is not a training sample")
    return rows


def prepare(manifest, data_root):
    root = Path(data_root).resolve()
    with Path(manifest).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise ValueError("Use the header from docs/templates/punch-dataset.csv")
        entries = list(reader)
    if not entries:
        raise ValueError("Manifest kosong; dataset nyata belum tersedia")
    identifiers, groups, videos, samples, signatures = set(), {}, set(), [], set()
    for entry in entries:
        if None in entry or any(value is None for value in entry.values()):
            raise ValueError("Malformed manifest columns")
        entry = {key: value.strip() for key, value in entry.items()}
        for key in FIELDS[:-2]:
            if not entry[key].strip():
                raise ValueError("Required manifest metadata missing: " + key)
        if entry["sampleId"] in identifiers:
            raise ValueError("Duplicate sampleId")
        identifiers.add(entry["sampleId"])
        if (
            entry["split"] not in SPLITS
            or entry["label"] not in LABELS
            or entry["labelSource"] not in SOURCES
        ):
            raise ValueError("Unknown split, label or labelSource")
        if (entry["label"] == "unlabeled") != (entry["labelSource"] == "unlabeled"):
            raise ValueError("Unlabeled samples must not claim a reviewed label")
        if (
            entry["labelSource"] == "user_reports_coach_demo"
            and entry["label"] != "correct"
        ):
            raise ValueError(
                "Coach demonstration provenance is only a reported correct reference"
            )
        if entry["cameraView"] != "front":
            raise ValueError(
                "This experiment currently requires the agreed front camera view"
            )
        observation_path = private_file(root, entry["observationsPath"])
        content = observation_path.read_bytes()
        report = json.loads(content)
        if (
            report.get("schemaVersion") != 1
            or report.get("experiment") != "pukulan-front-elbow-diagnostic-v1"
            or report.get("movementSlug") != "pukulan"
            or report.get("cameraView") != "front_as_input_assumption"
        ):
            raise ValueError(
                "Incompatible observations; run analyze_punch_reference first"
            )
        video_hash = report["sourceVideoSha256"]
        model_hash = report["poseModelSha256"]
        if not all(
            isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)
            for value in (video_hash, model_hash)
        ):
            raise ValueError("Missing or invalid source/model fingerprint")
        for key, value in [
            ("participantId", entry["participantId"]),
            ("recordingId", entry["recordingId"]),
            ("video", video_hash),
        ]:
            group = (key, value)
            if group in groups and groups[group] != entry["split"]:
                raise ValueError("Cross-split data leakage: " + key)
            groups[group] = entry["split"]
        if video_hash in videos:
            raise ValueError("Duplicate video content is not an independent sample")
        videos.add(video_hash)
        phases = report.get("manualPhases")
        if entry["annotationsPath"]:
            phases = json.loads(
                private_file(root, entry["annotationsPath"]).read_text(encoding="utf-8")
            )
        if phases is not None:
            phases = validate_phases(phases, report["video"]["durationSeconds"])
        signature = json.dumps(
            dict(
                experiment=report["experiment"],
                model=model_hash,
                versions=report["versions"],
                visibilityThreshold=report["sampling"]["visibilityThreshold"],
            ),
            sort_keys=True,
        )
        signatures.add(signature)
        samples.append(
            {
                **{
                    key: value
                    for key, value in entry.items()
                    if key not in {"observationsPath", "annotationsPath"}
                },
                "sourceVideoSha256": video_hash,
                "observationsSha256": hashlib.sha256(content).hexdigest(),
                "manualPhases": phases,
                "frames": sequence(report, phases),
            }
        )
    if len(signatures) != 1:
        raise ValueError(
            "Pose model/dependency/visibility versions differ; extract a consistent dataset"
        )
    splits = Counter(sample["split"] for sample in samples)
    train_labels = {
        sample["label"]
        for sample in samples
        if sample["split"] == "train" and sample["label"] != "unlabeled"
    }
    missing = ["missing_" + split + "_split" for split in sorted(SPLITS - set(splits))]
    if train_labels != {"correct", "needs_correction"}:
        missing.append("binary_training_labels_incomplete")
    if any(sample["label"] == "unlabeled" for sample in samples):
        missing.append("unlabeled_samples_remain")
    return dict(
        schemaVersion=1,
        experiment="pukulan-temporal-dataset-v1",
        extractionSignature=json.loads(next(iter(signatures))),
        sampleCount=len(samples),
        splitCounts=dict(splits),
        labelCounts=dict(Counter(sample["label"] for sample in samples)),
        dataStructureComplete=not missing,
        structuralGaps=missing,
        trainedModelCreated=False,
        qualityAssessmentValidated=False,
        pendingRequirements=[
            "front_view_measurement_validation",
            "correctness_label_rubric",
            "independent_test_review",
        ],
        samples=samples,
    )
