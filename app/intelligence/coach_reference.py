"""Learn correct-Coach references, align users, and explain local deviations."""

from collections import Counter
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

from app.intelligence.movement_catalog import MOVEMENTS
from app.intelligence.movement_dataset import validate_report
from app.intelligence.movement_features import (
    FAMILY_FEATURES,
    FEATURE_UNITS,
    FEATURE_VERSION,
    TRIPLES,
)
from app.intelligence.movement_training import BINS
from app.intelligence.punch_dataset import private_file
from app.intelligence.punch_diagnostics import phase_at, validate_phases
from app.intelligence.reference_alignment import WARP_RADIUS, align, sequence

MODEL_TYPE = "correct-coach-reference-v1"
FIELDS = (
    "sampleId",
    "participantId",
    "recordingId",
    "split",
    "movementId",
    "referenceSource",
    "observationsPath",
    "annotationsPath",
)
SOURCES = {"user_confirmed_coach_demo", "coach_reviewed_correct"}


def prepare(manifest, data_root):
    root = Path(data_root).resolve()
    with Path(manifest).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise ValueError("Use docs/templates/coach-references.csv header")
        entries = list(reader)
    samples = []
    for row in entries:
        if None in row or any(value is None for value in row.values()):
            raise ValueError("Malformed reference manifest")
        row = {key: value.strip() for key, value in row.items()}
        if any(not row[key] for key in FIELDS if key != "annotationsPath"):
            raise ValueError("Reference metadata missing")
        content = private_file(root, row["observationsPath"]).read_bytes()
        report = validate_report(json.loads(content))
        phases = None
        if row["annotationsPath"]:
            phases = validate_phases(
                json.loads(
                    private_file(root, row["annotationsPath"]).read_text(
                        encoding="utf-8"
                    )
                ),
                report["video"]["durationSeconds"],
            )
        samples.append(
            {
                **{
                    key: value
                    for key, value in row.items()
                    if key not in {"observationsPath", "annotationsPath"}
                },
                "referenceIsCorrect": True,
                "observationsSha256": hashlib.sha256(content).hexdigest(),
                "manualPhases": phases,
                "observations": report,
            }
        )
    dataset = {"datasetType": MODEL_TYPE, "samples": samples}
    validate_dataset(dataset)
    return dataset


def validate_dataset(dataset):
    if dataset.get("datasetType") != MODEL_TYPE or not dataset.get("samples"):
        raise ValueError("A nonempty correct-Coach reference dataset is required")
    ids, videos, groups, signatures = set(), set(), {}, set()
    for sample in dataset["samples"]:
        if sample.get("movementId") not in MOVEMENTS or sample.get("split") not in {
            "train",
            "validation",
            "test",
        }:
            raise ValueError("Unknown movement or split")
        if (
            sample.get("referenceIsCorrect") is not True
            or sample.get("referenceSource") not in SOURCES
        ):
            raise ValueError(
                "Only confirmed correct Coach demonstrations may build references"
            )
        if not sample.get("sampleId") or sample["sampleId"] in ids:
            raise ValueError("Duplicate or missing sampleId")
        ids.add(sample["sampleId"])
        report = validate_report(sample["observations"])
        video = report["sourceVideoSha256"]
        if video in videos:
            raise ValueError("Duplicate video content")
        videos.add(video)
        for key in ("participantId", "recordingId"):
            if not sample.get(key):
                raise ValueError("Missing Coach or recording identity")
            group = (key, sample[key])
            if group in groups and groups[group] != sample["split"]:
                raise ValueError("Cross-split data leakage: " + key)
            groups[group] = sample["split"]
        if sample.get("manualPhases") is not None:
            validate_phases(sample["manualPhases"], report["video"]["durationSeconds"])
        signatures.add(json.dumps(report["extractionSignature"], sort_keys=True))
    if len(signatures) != 1:
        raise ValueError("Reference extraction configurations must match")
    return json.loads(next(iter(signatures)))


def _array(values):
    if (
        not isinstance(values, list)
        or any(not isinstance(row, list) for row in values)
        or any(
            v is not None
            and (
                isinstance(v, bool)
                or not isinstance(v, (int, float))
                or not np.isfinite(v)
            )
            for row in values
            for v in row
        )
    ):
        raise ValueError("Reference sequences must contain finite numbers or null")
    return np.asarray(
        [[np.nan if x is None else x for x in row] for row in values], float
    )


def _json_array(array):
    return [[float(x) if np.isfinite(x) else None for x in row] for row in array]


def _nearest(matrix, templates, names):
    candidates = []
    for template in templates:
        try:
            aligned = align(matrix, _array(template["sequence"]), names)
            candidates.append((aligned["distance"], template, aligned))
        except ValueError:
            continue
    if not candidates:
        raise ValueError("No reference with sufficient paired visibility")
    return min(candidates, key=lambda item: item[0])[1:]


def _tolerances(templates, names):
    """Leave each Coach out; held-out validation/test never sets color bounds."""
    coaches = sorted({t["participantId"] for t in templates})
    thresholds = dict.fromkeys(names)
    if len(coaches) < 3:
        return thresholds, "insufficient_independent_coaches"
    bounds = {name: [] for name in names}
    for coach in coaches:
        others = [t for t in templates if t["participantId"] != coach]
        pooled = {name: [] for name in names}
        for template in (t for t in templates if t["participantId"] == coach):
            try:
                _, matched = _nearest(_array(template["sequence"]), others, names)
            except ValueError:
                continue
            for i, name in enumerate(names):
                values = matched["deviations"][:, i]
                pooled[name].extend(values[np.isfinite(values)].tolist())
        for name in names:
            if len(pooled[name]) >= 8:
                bounds[name].append(np.quantile(pooled[name], [0.9, 0.99]))
    for name, pairs in bounds.items():
        if len(pairs) == len(coaches):
            yellow, red = np.max(pairs, axis=0)
            if 0 < yellow < red:
                thresholds[name] = {
                    "yellowAbove": float(yellow),
                    "redAbove": float(red),
                    "unit": FEATURE_UNITS[name],
                    "coachCount": len(coaches),
                }
    return thresholds, "experimental_coach_variation" if any(
        thresholds.values()
    ) else "variation_not_estimable"


def fit(dataset):
    signature = validate_dataset(dataset)
    profiles = {}
    for movement in sorted({s["movementId"] for s in dataset["samples"]}):
        names = list(FAMILY_FEATURES[MOVEMENTS[movement][0]])
        templates = []
        for sample in dataset["samples"]:
            if sample["split"] != "train" or sample["movementId"] != movement:
                continue
            matrix = sequence(sample["observations"], names)
            align(matrix, matrix, names)  # Family-specific observability gate.
            templates.append(
                {
                    "sampleId": sample["sampleId"],
                    "participantId": sample["participantId"],
                    "recordingId": sample["recordingId"],
                    "sourceVideoSha256": sample["observations"]["sourceVideoSha256"],
                    "durationSeconds": sample["observations"]["video"][
                        "durationSeconds"
                    ],
                    "manualPhases": sample.get("manualPhases"),
                    "sequence": _json_array(matrix),
                }
            )
        if not templates:
            raise ValueError("No training references for " + movement)
        tolerances, status = _tolerances(templates, names)
        profiles[movement] = {
            "featureNames": names,
            "templates": templates,
            "tolerances": tolerances,
            "toleranceStatus": status,
            "coachCount": len({t["participantId"] for t in templates}),
        }
    return {
        "schemaVersion": 1,
        "modelType": MODEL_TYPE,
        "featureVersion": FEATURE_VERSION,
        "temporalBins": BINS,
        "warpRadius": WARP_RADIUS,
        "extractionSignature": signature,
        "datasetSha256": hashlib.sha256(
            json.dumps(dataset, sort_keys=True, allow_nan=False).encode()
        ).hexdigest(),
        "splitCounts": dict(Counter(s["split"] for s in dataset["samples"])),
        "profiles": profiles,
        "qualityAssessmentValidated": False,
        "productionReady": False,
    }


def _check_model(model, movement, report):
    validate_report(report)
    if (
        model.get("schemaVersion") != 1
        or model.get("modelType") != MODEL_TYPE
        or model.get("featureVersion") != FEATURE_VERSION
        or model.get("temporalBins") != BINS
        or model.get("warpRadius") != WARP_RADIUS
    ):
        raise ValueError("Incompatible reference artifact")
    if movement not in MOVEMENTS or movement not in model.get("profiles", {}):
        raise ValueError("No reference profile for requested movement")
    if model["extractionSignature"] != report["extractionSignature"]:
        raise ValueError("Use the same pose model and extraction configuration")
    profile = model["profiles"][movement]
    names = list(FAMILY_FEATURES[MOVEMENTS[movement][0]])
    if (
        profile["featureNames"] != names
        or not profile.get("templates")
        or set(profile["tolerances"]) != set(names)
    ):
        raise ValueError("Invalid reference feature schema")
    for template in profile["templates"]:
        array = _array(template["sequence"])
        if array.shape != (BINS, len(names)) or np.isinf(array).any():
            raise ValueError("Invalid reference sequence")
    for name, threshold in profile["tolerances"].items():
        if threshold is not None:
            values = [threshold.get("yellowAbove"), threshold.get("redAbove")]
            if (
                any(
                    isinstance(v, bool)
                    or not isinstance(v, (int, float))
                    or not np.isfinite(v)
                    for v in values
                )
                or not 0 < values[0] < values[1]
                or threshold.get("unit") != FEATURE_UNITS[name]
            ):
                raise ValueError("Invalid color tolerance")
    return profile, names


def compare(model, report, movement):
    profile, names = _check_model(model, movement, report)
    result = {
        "movementId": movement,
        "experimental": True,
        "correctness": None,
        "score": None,
        "qualityAssessmentValidated": False,
        "toleranceStatus": profile["toleranceStatus"],
        "sourceVideoSha256": report["sourceVideoSha256"],
        "frames": [],
        "features": {},
    }
    try:
        matrix = sequence(report, names)
        template, aligned = _nearest(matrix, profile["templates"], names)
    except ValueError as error:
        return {**result, "status": "not_assessable", "reason": str(error)}
    for i in range(BINS):
        reference_seconds = (
            aligned["referenceBins"][i] / BINS * template["durationSeconds"]
        )
        frame = {
            "timeSeconds": i / BINS * report["video"]["durationSeconds"],
            "referenceTimeSeconds": reference_seconds,
            "phase": phase_at(reference_seconds, template.get("manualPhases")),
            "features": {},
            "joints": {},
        }
        for k, name in enumerate(names):
            value, target, deviation = (
                matrix[i, k],
                aligned["matched"][i, k],
                aligned["deviations"][i, k],
            )
            tolerance = profile["tolerances"][name]
            color = None
            if np.isfinite(deviation) and tolerance is not None:
                color = (
                    "red"
                    if deviation > tolerance["redAbove"]
                    else "yellow"
                    if deviation > tolerance["yellowAbove"]
                    else "green"
                )
            reason = (
                "joint_not_observable"
                if not np.isfinite(deviation)
                else "tolerance_pending"
                if tolerance is None
                else None
            )
            item = {
                "value": float(value) if np.isfinite(value) else None,
                "referenceValue": float(target) if np.isfinite(target) else None,
                "deviation": float(deviation) if np.isfinite(deviation) else None,
                "unit": FEATURE_UNITS[name],
                "color": color,
                "reason": reason,
            }
            frame["features"][name] = item
            if name in TRIPLES:
                joint = name.removesuffix("_deg")
                feedback = None
                if color in {"yellow", "red"}:
                    feedback = (
                        "lebih_menekuk_dari_referensi"
                        if "elbow" in name or "knee" in name
                        else "sudut_berbeda_dari_referensi"
                    )
                    if feedback == "lebih_menekuk_dari_referensi" and value > target:
                        feedback = "lebih_lurus_dari_referensi"
                frame["joints"][joint] = {
                    **item,
                    "landmarkIndices": list(TRIPLES[name]),
                    "feedbackCode": feedback,
                }
        result["frames"].append(frame)
    for name in names:
        items = [f["features"][name] for f in result["frames"]]
        values = [x["deviation"] for x in items if x["deviation"] is not None]
        result["features"][name] = {
            "sampleCount": len(values),
            "coverage": len(values) / BINS,
            "medianDeviation": float(np.median(values)) if values else None,
            "maximumDeviation": max(values) if values else None,
            "unit": FEATURE_UNITS[name],
            "colorCounts": dict(
                Counter(x["color"] for x in items if x["color"] is not None)
            ),
        }
    return {
        **result,
        "status": "compared",
        "referenceSampleId": template["sampleId"],
        "isReferenceReplay": any(
            report["sourceVideoSha256"] == t["sourceVideoSha256"]
            for t in profile["templates"]
        ),
        "alignmentDistance": aligned["distance"],
        "semanticPhasesAvailable": bool(template.get("manualPhases")),
    }


def evaluate(model, dataset, split):
    validate_dataset(dataset)
    if split not in {"validation", "test"}:
        raise ValueError("Evaluation requires held-out validation or test")
    trained_coaches = {
        t["participantId"] for p in model["profiles"].values() for t in p["templates"]
    }
    trained_videos = {
        t["sourceVideoSha256"]
        for p in model["profiles"].values()
        for t in p["templates"]
    }
    trained_recordings = {
        t["recordingId"] for p in model["profiles"].values() for t in p["templates"]
    }
    rows = []
    for sample in dataset["samples"]:
        if sample["split"] != split:
            continue
        if (
            sample["participantId"] in trained_coaches
            or sample["recordingId"] in trained_recordings
            or sample["observations"]["sourceVideoSha256"] in trained_videos
        ):
            raise ValueError("Held-out Coach/video overlaps training references")
        report = compare(model, sample["observations"], sample["movementId"])
        colored = [
            item["color"]
            for f in report["frames"]
            for item in f["features"].values()
            if item["color"] is not None
        ]
        rows.append(
            {
                "sampleId": sample["sampleId"],
                "movementId": sample["movementId"],
                "status": report["status"],
                "coloredObservationCount": len(colored),
                "correctReferenceFlagRate": sum(c != "green" for c in colored)
                / len(colored)
                if colored
                else None,
            }
        )
    return {
        "split": split,
        "sampleCount": len(rows),
        "samples": rows,
        "correctnessAccuracy": None,
        "reason": "Correct-only references cannot measure sensitivity to beginner mistakes",
        "qualityAssessmentValidated": False,
    }
