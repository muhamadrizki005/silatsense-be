"""Small NumPy temporal nearest-centroid baseline; classification, never grading."""

from collections import Counter
import hashlib
import json

import numpy as np

from app.intelligence.movement_catalog import MOVEMENTS
from app.intelligence.movement_dataset import SPLITS, validate_report
from app.intelligence.movement_features import (
    FEATURE_NAMES,
    FEATURE_UNITS,
    FEATURE_VERSION,
)

BINS = 32
MAX_GAP_SECONDS = 0.15
MIN_COVERAGE = 0.5
MODEL_TYPE = "movement-temporal-centroid-v1"


def temporal_vector(report):
    """Nearest observations only; long gaps remain missing, never interpolated."""
    validate_report(report)
    rows = report["frames"]
    if len(rows) < 8:
        raise ValueError("At least eight sampled frames are required")
    times = np.array([r["timeSeconds"] for r in rows])
    targets = np.linspace(0, report["video"]["durationSeconds"], BINS, endpoint=False)
    nearest = np.abs(targets[:, None] - times).argmin(axis=1)
    values = np.array(
        [
            [
                np.nan if row["features"][n] is None else row["features"][n]
                for n in FEATURE_NAMES
            ]
            for row in rows
        ],
        dtype=float,
    )
    matrix = values[nearest].copy()
    matrix[np.abs(times[nearest] - targets) > MAX_GAP_SECONDS] = np.nan
    if (
        np.isfinite(matrix).mean() < MIN_COVERAGE
        or (np.isfinite(values).mean(axis=1) >= MIN_COVERAGE).sum() < 8
    ):
        raise ValueError(
            "Insufficient observable pose coverage; re-record or review extraction"
        )
    return matrix.ravel()


def metrics(truth, predicted, classes):
    confusion = [
        [sum(a == c and b == d for a, b in zip(truth, predicted)) for d in classes]
        for c in classes
    ]
    per_class = {}
    for i, name in enumerate(classes):
        tp, support = confusion[i][i], sum(confusion[i])
        selected = sum(row[i] for row in confusion)
        precision = tp / selected if selected else 0.0
        recall = tp / support if support else None
        f1 = 2 * tp / (support + selected) if support + selected else None
        per_class[name] = {
            "sampleCount": support,
            "precision": precision if selected else None,
            "recall": recall,
            "f1": f1,
        }
    scored = [v["f1"] for v in per_class.values() if v["f1"] is not None]
    return {
        "sampleCount": len(truth),
        "accuracy": sum(a == b for a, b in zip(truth, predicted)) / len(truth)
        if truth
        else None,
        "macroF1": float(np.mean(scored)) if scored else None,
        "classes": classes,
        "confusionMatrix": confusion,
        "perClass": per_class,
    }


def _transform(vectors, mean, scale):
    observed = np.isfinite(vectors)
    # Train-only means fill missing features internally. Explicit masks retain
    # missingness, while raw observation artifacts continue to contain null.
    filled = np.where(observed, vectors, mean)
    return np.concatenate(((filled - mean) / scale, observed.astype(float)), axis=1)


def _labels(matrix, centroids, classes):
    distances = np.linalg.norm(matrix[:, None, :] - centroids[None, :, :], axis=2)
    return [classes[i] for i in distances.argmin(axis=1)]


def train(dataset):
    if (
        dataset.get("datasetType") != "movement-recognition-v1"
        or dataset.get("featureVersion") != FEATURE_VERSION
    ):
        raise ValueError("Incompatible prepared dataset")
    samples = dataset["samples"]
    groups, identifiers, hashes = {}, set(), set()
    classes = sorted(MOVEMENTS)
    vectors = {s: [] for s in SPLITS}
    labels = {s: [] for s in SPLITS}
    for sample in samples:
        split, label = sample["split"], sample["movementId"]
        if split not in SPLITS or label not in MOVEMENTS:
            raise ValueError("Unknown split or movement")
        if sample.get("labelSource") not in {
            "coach_review",
            "user_confirmed_reference",
        }:
            raise ValueError("Movement label provenance is required")
        if not sample.get("sampleId") or sample["sampleId"] in identifiers:
            raise ValueError("Missing or duplicate sampleId")
        identifiers.add(sample["sampleId"])
        report = validate_report(sample["observations"])
        if (
            report["extractionSignature"] != dataset["extractionSignature"]
            or report["poseModelSha256"]
            != dataset["extractionSignature"]["poseModelSha256"]
        ):
            raise ValueError("Extraction signature mismatch")
        video_hash = report["sourceVideoSha256"]
        if video_hash in hashes:
            raise ValueError("Duplicate source video")
        hashes.add(video_hash)
        for key, value in (
            ("participantId", sample.get("participantId")),
            ("recordingId", sample.get("recordingId")),
        ):
            if not value:
                raise ValueError("Missing participant or recording identity")
            group = (key, value)
            if group in groups and groups[group] != split:
                raise ValueError("Cross-split data leakage: " + key)
            groups[group] = split
        vectors[split].append(temporal_vector(report))
        labels[split].append(label)
    for split in sorted(SPLITS):
        counts = Counter(labels[split])
        minimum = 2 if split == "train" else 1
        missing = [c for c in classes if counts[c] < minimum]
        if missing:
            raise ValueError(
                f"{split}: need >= {minimum} independent videos per movement; missing: "
                + ", ".join(missing)
            )
    training = np.array(vectors["train"])
    observed = np.isfinite(training)
    observed_counts = observed.sum(axis=0)
    mean = np.divide(
        np.nansum(training, axis=0),
        observed_counts,
        out=np.zeros(training.shape[1]),
        where=observed_counts > 0,
    )
    filled = np.where(observed, training, mean)
    scale = filled.std(axis=0)
    scale[scale < 1e-8] = 1
    transformed = _transform(training, mean, scale)
    centroids = np.array(
        [transformed[np.array(labels["train"]) == c].mean(axis=0) for c in classes]
    )
    evaluations = {}
    for split in ("validation", "test"):
        predicted = _labels(
            _transform(np.array(vectors[split]), mean, scale), centroids, classes
        )
        evaluations[split] = metrics(labels[split], predicted, classes)
    fingerprint = hashlib.sha256(
        json.dumps(dataset, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()
    return {
        "schemaVersion": 1,
        "modelType": MODEL_TYPE,
        "featureVersion": FEATURE_VERSION,
        "featureNames": list(FEATURE_NAMES),
        "featureUnits": FEATURE_UNITS,
        "temporalBins": BINS,
        "maxGapSeconds": MAX_GAP_SECONDS,
        "minimumCoverage": MIN_COVERAGE,
        "extractionSignature": dataset["extractionSignature"],
        "classes": classes,
        "trainMean": mean.tolist(),
        "trainScale": scale.tolist(),
        "centroids": centroids.tolist(),
        "trainObservedCounts": observed_counts.tolist(),
        "datasetSha256": fingerprint,
        "trainingSampleCount": len(training),
        "evaluations": evaluations,
        "qualityAssessmentValidated": False,
        "productionReady": False,
        "limitations": [
            "closed_set_baseline_no_unknown_rejection",
            "distances_are_not_probabilities",
            "fixed_front_camera",
            "image_angles_are_projections",
            "no_correctness_rubric",
            "no_automatic_phase_alignment",
            "split_minimums_do_not_establish_sufficiency",
        ],
    }


def predict(model, report):
    if (
        model.get("modelType") != MODEL_TYPE
        or model.get("schemaVersion") != 1
        or model.get("featureVersion") != FEATURE_VERSION
        or model.get("featureNames") != list(FEATURE_NAMES)
        or model.get("temporalBins") != BINS
        or model.get("maxGapSeconds") != MAX_GAP_SECONDS
        or model.get("minimumCoverage") != MIN_COVERAGE
        or model.get("classes") != sorted(MOVEMENTS)
    ):
        raise ValueError("Incompatible model artifact")
    if model["extractionSignature"] != report["extractionSignature"]:
        raise ValueError(
            "Extract with the same configuration and pose model used in training"
        )
    vector = temporal_vector(report)
    mean, scale, centroids = (
        np.asarray(model[k], dtype=float)
        for k in ("trainMean", "trainScale", "centroids")
    )
    size = BINS * len(FEATURE_NAMES)
    if (
        mean.shape != (size,)
        or scale.shape != (size,)
        or centroids.shape != (len(MOVEMENTS), size * 2)
        or not all(np.isfinite(a).all() for a in (mean, scale, centroids))
        or (scale <= 0).any()
    ):
        raise ValueError("Invalid model dimensions or parameters")
    transformed = _transform(vector[None, :], mean, scale)
    distances = np.linalg.norm(transformed[0] - centroids, axis=1)
    selected = int(distances.argmin())
    return {
        "movementId": model["classes"][selected],
        "distance": float(distances[selected]),
        "distanceUnit": "standardized_feature_space",
        "confidence": None,
        "qualityAssessment": None,
        "experimental": True,
        "unknownRejectionSupported": False,
    }
