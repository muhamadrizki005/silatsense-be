"""Synthetic fixtures verify plumbing only, never real recognition accuracy."""

import copy
import csv
import hashlib
import json

import numpy as np
import pytest

from app.intelligence.movement_catalog import MOVEMENTS
from app.intelligence.movement_dataset import FIELDS, prepare, validate_report
from app.intelligence.movement_features import (
    FEATURE_NAMES,
    FEATURE_VERSION,
    extract_features,
)
from app.intelligence.movement_training import metrics, predict, temporal_vector, train
from scripts.movement_pipeline import write


def observation(identity, value=30.0):
    model_hash = "a" * 64
    signature = {
        "featureVersion": FEATURE_VERSION,
        "poseModelSha256": model_hash,
        "sampleFpsRequested": 15,
        "visibilityThreshold": 0.5,
        "maximumImageDimension": 1280,
        "cameraView": "front_fixed_as_input_assumption",
        "versions": {
            "numpy": "test",
            "mediapipe": "test",
            "opencv-contrib-python": "test",
        },
    }
    return {
        "schemaVersion": 1,
        "featureVersion": FEATURE_VERSION,
        "sourceVideoSha256": hashlib.sha256(identity.encode()).hexdigest(),
        "poseModelSha256": model_hash,
        "cameraView": "front_fixed_as_input_assumption",
        "extractionSignature": signature,
        "video": {"durationSeconds": 2.0},
        "frames": [
            {
                "timeSeconds": i / 16,
                "features": {n: value + i / 100 for n in FEATURE_NAMES},
                "unavailableReasons": dict.fromkeys(FEATURE_NAMES),
            }
            for i in range(32)
        ],
    }


@pytest.fixture
def dataset():
    samples = []
    for split, repetitions in (("train", 2), ("validation", 1), ("test", 1)):
        for index, movement in enumerate(sorted(MOVEMENTS)):
            for repeat in range(repetitions):
                identity = f"{split}-{movement}-{repeat}"
                samples.append(
                    {
                        "sampleId": identity,
                        "participantId": f"{split}-{repeat}",
                        "recordingId": identity,
                        "split": split,
                        "movementId": movement,
                        "labelSource": "coach_review",
                        "qualityLabel": "unlabeled",
                        "observations": observation(identity, 10 + index * 10 + repeat),
                    }
                )
    return {
        "datasetType": "movement-recognition-v1",
        "featureVersion": FEATURE_VERSION,
        "extractionSignature": samples[0]["observations"]["extractionSignature"],
        "samples": samples,
    }


def test_features_geometry_and_translation_scale_invariance():
    p = np.zeros((33, 4))
    p[:, 3] = 1
    for i, xy in {
        11: (0, 1),
        12: (2, 1),
        23: (0, 3),
        24: (2, 3),
        13: (1, 1),
        15: (1, 2),
        27: (-1, 5),
        28: (3, 5),
    }.items():
        p[i, :2] = xy
    first = extract_features(p)["values"]
    assert first["left_elbow_deg"] == pytest.approx(90)
    assert first["stance_width_torso"] == pytest.approx(2)
    p[:, :2] = p[:, :2] * 3 + [7, -2]
    assert extract_features(p)["values"] == pytest.approx(first)
    p[13, 3] = 0
    result = extract_features(p)
    assert result["values"]["left_elbow_deg"] is None
    assert result["unavailableReasons"]["left_elbow_deg"]
    assert result["values"]["stance_width_torso"] is not None


def test_missing_pose_never_fabricates_features():
    report = extract_features(None)
    assert all(v is None for v in report["values"].values())
    assert set(report["unavailableReasons"].values()) == {"pose_unavailable"}


@pytest.mark.parametrize(
    "change", ["unordered", "negative_time", "nan", "missing_reason", "angle", "empty"]
)
def test_invalid_observations(change):
    report = observation("one")
    if change == "unordered":
        report["frames"][1]["timeSeconds"] = 0
    elif change == "negative_time":
        report["frames"][0]["timeSeconds"] = -0.1
    elif change == "nan":
        report["frames"][0]["features"][FEATURE_NAMES[0]] = float("nan")
    elif change == "missing_reason":
        report["frames"][0]["features"][FEATURE_NAMES[0]] = None
    elif change == "angle":
        report["frames"][0]["features"][FEATURE_NAMES[0]] = 181
    else:
        report["frames"] = []
    with pytest.raises(ValueError):
        validate_report(report)


def test_long_gaps_are_missing_and_bad_coverage_is_rejected():
    report = observation("one")
    report["frames"] = report["frames"][:12] + report["frames"][24:]
    assert np.isnan(temporal_vector(report)).any()
    report["frames"] = report["frames"][:8]
    with pytest.raises(ValueError, match="coverage"):
        temporal_vector(report)


def save_manifest(tmp_path, dataset):
    rows = []
    for i, sample in enumerate(dataset["samples"]):
        name = f"{i}.json"
        (tmp_path / name).write_text(
            json.dumps(sample["observations"]), encoding="utf-8"
        )
        rows.append(
            {
                **{k: sample[k] for k in FIELDS if k != "observationsPath"},
                "observationsPath": name,
            }
        )
    manifest = tmp_path / "manifest.csv"
    with manifest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return manifest


def test_prepare_train_save_reload_predict(tmp_path, dataset):
    manifest = save_manifest(tmp_path, dataset)
    prepared = prepare(manifest, tmp_path)
    assert prepared["sampleCount"] == 48
    assert prepared["qualityAssessmentValidated"] is False
    model = train(prepared)
    path = tmp_path / "model.json"
    write(path, model)
    restored = json.loads(path.read_text())
    for sample in dataset["samples"]:
        if sample["split"] == "test":
            result = predict(restored, sample["observations"])
            assert result["movementId"] == sample["movementId"]
            assert result["confidence"] is None and result["qualityAssessment"] is None
    assert restored["evaluations"]["test"]["sampleCount"] == 12
    assert restored["productionReady"] is False
    with pytest.raises(FileExistsError):
        write(path, model)


@pytest.mark.parametrize(
    "kind",
    ["participant", "recording", "video", "sample", "signature", "missing_class"],
)
def test_train_rechecks_integrity(dataset, kind):
    a, b = dataset["samples"][0], dataset["samples"][-1]
    if kind in {"participant", "recording", "sample"}:
        b[kind + "Id"] = a[kind + "Id"]
    elif kind == "video":
        b["observations"]["sourceVideoSha256"] = a["observations"]["sourceVideoSha256"]
    elif kind == "signature":
        b["observations"]["extractionSignature"] = copy.deepcopy(
            b["observations"]["extractionSignature"]
        )
        b["observations"]["extractionSignature"]["visibilityThreshold"] = 0.8
    else:
        dataset["samples"].pop()
    with pytest.raises(ValueError):
        train(dataset)


def test_test_data_does_not_fit_normalizer_or_centroids(dataset):
    first = train(dataset)
    for sample in dataset["samples"]:
        if sample["split"] != "train":
            for row in sample["observations"]["frames"]:
                row["features"] = dict.fromkeys(FEATURE_NAMES, 179)
    second = train(dataset)
    for name in ("trainMean", "trainScale", "centroids"):
        assert first[name] == second[name]
    assert first["evaluations"] != second["evaluations"]


@pytest.mark.parametrize(
    "kind", ["escape", "quality", "duplicate", "signature", "leak"]
)
def test_manifest_rejects_invalid_data(tmp_path, dataset, kind):
    if kind == "quality":
        dataset["samples"][0].update(
            labelSource="user_confirmed_reference", qualityLabel="correct"
        )
    elif kind == "duplicate":
        dataset["samples"][1]["observations"] = dataset["samples"][0]["observations"]
    elif kind == "signature":
        dataset["samples"][1]["observations"]["extractionSignature"] = {}
    elif kind == "leak":
        dataset["samples"][-1]["participantId"] = dataset["samples"][0]["participantId"]
    manifest = save_manifest(tmp_path, dataset)
    if kind == "escape":
        manifest.write_text(manifest.read_text().replace("0.json", "../outside.json"))
    with pytest.raises(ValueError):
        prepare(manifest, tmp_path)


@pytest.mark.parametrize("kind", ["schema", "nan", "shape", "scale", "extraction"])
def test_predict_rejects_incompatible_artifacts(dataset, kind):
    model = train(dataset)
    report = dataset["samples"][0]["observations"]
    if kind == "schema":
        model["featureNames"] = []
    elif kind == "nan":
        model["trainMean"][0] = float("nan")
    elif kind == "shape":
        model["centroids"] = [[1]]
    elif kind == "scale":
        model["trainScale"][0] = 0
    else:
        report = copy.deepcopy(report)
        report["extractionSignature"]["sampleFpsRequested"] = 2
    with pytest.raises(ValueError):
        predict(model, report)


def test_metrics_keep_sample_counts_and_errors_visible():
    result = metrics(["a", "a", "b"], ["a", "b", "b"], ["a", "b"])
    assert result["confusionMatrix"] == [[1, 1], [0, 1]]
    assert result["accuracy"] == pytest.approx(2 / 3)
    assert result["macroF1"] == pytest.approx(2 / 3)
    assert metrics([], [], ["a"])["accuracy"] is None


def test_nonfinite_artifact_does_not_create_partial_file(tmp_path):
    path = tmp_path / "invalid.json"
    with pytest.raises(ValueError):
        write(path, {"value": float("nan")})
    assert not path.exists()


def test_native_video_extraction_lifecycle_and_missing_pose(tmp_path, monkeypatch):
    import cv2
    from app.intelligence.contracts import Pose
    from app.intelligence.pose import mediapipe_extractor
    from app.intelligence.movement_video import extract_video

    video, model = tmp_path / "input.mp4", tmp_path / "pose.task"
    video.write_bytes(b"private fixture")
    model.write_bytes(b"fixture model, not a real asset")
    closed = []

    class Capture:
        index = 0

        def set(self, *args):
            pass

        def isOpened(self):
            return True

        def get(self, key):
            return 10 if key in (cv2.CAP_PROP_FPS, cv2.CAP_PROP_FRAME_COUNT) else 0

        def read(self):
            self.index += 1
            return (
                (True, np.zeros((480, 640, 3), dtype=np.uint8))
                if self.index <= 10
                else (False, None)
            )

        def release(self):
            closed.append("capture")

    class Extractor:
        def __init__(self, path):
            self.count = 0

        def extract(self, rgb):
            self.count += 1
            if self.count == 1:
                return None
            p = np.zeros((33, 4))
            p[:, :2] = 0.5
            p[:, 3] = 1
            p[11:13, 1] = 0.2
            return Pose(p)

        def close(self):
            closed.append("extractor")

    monkeypatch.setattr(cv2, "VideoCapture", lambda path: Capture())
    monkeypatch.setattr(mediapipe_extractor, "MediaPipePoseExtractor", Extractor)
    report = extract_video(video, model)
    assert report["video"]["decodedFrameCount"] == 10
    assert report["frames"][0]["features"]["left_elbow_deg"] is None
    assert (
        report["frames"][0]["unavailableReasons"]["left_elbow_deg"]
        == "pose_unavailable"
    )
    assert report["qualityAssessment"] is None
    validate_report(report)
    assert closed == ["capture", "extractor"]
    with pytest.raises(ValueError, match="duration"):
        extract_video(video, model, max_seconds=0.5)
    assert closed[-1] == "capture"


@pytest.mark.parametrize(
    "setting",
    [
        {"sample_fps": 0},
        {"sample_fps": float("nan")},
        {"visibility": 2},
        {"max_seconds": -1},
    ],
)
def test_invalid_video_settings_are_rejected(tmp_path, setting):
    from app.intelligence.movement_video import extract_video

    with pytest.raises(ValueError, match="settings"):
        extract_video(tmp_path / "absent.mp4", tmp_path / "absent.task", **setting)
