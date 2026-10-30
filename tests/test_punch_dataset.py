import csv
import hashlib
import json

import pytest

from app.intelligence.punch_dataset import FIELDS, prepare


def observation(identifier):
    measurement = dict(imageAngleDeg=90.0, estimatedWorldAngleDeg=None)
    return dict(
        schemaVersion=1,
        experiment="pukulan-front-elbow-diagnostic-v1",
        movementSlug="pukulan",
        cameraView="front_as_input_assumption",
        sourceVideoSha256=hashlib.sha256(identifier.encode()).hexdigest(),
        poseModelSha256="a" * 64,
        versions={"numpy": "test-only"},
        sampling={"visibilityThreshold": 0.5},
        video={"durationSeconds": 1.0},
        manualPhases=None,
        frames=[
            dict(
                frameIndex=index,
                timeSeconds=seconds,
                elbows={"left": measurement, "right": measurement},
            )
            for index, seconds in [(0, 0.0), (5, 0.5)]
        ],
    )


def write_manifest(tmp_path, rows):
    path = tmp_path / "manifest.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def sample(tmp_path, identifier="demo", split="train", label="correct"):
    (tmp_path / (identifier + ".json")).write_text(json.dumps(observation(identifier)))
    return dict(
        sampleId=identifier,
        participantId=identifier,
        recordingId=identifier,
        split=split,
        label=label,
        labelSource="coach_review",
        cameraView="front",
        observationsPath=identifier + ".json",
        annotationsPath="",
    )


def test_one_reported_coach_reference_is_not_a_complete_training_dataset(tmp_path):
    row = sample(tmp_path)
    row["labelSource"] = "user_reports_coach_demo"
    result = prepare(write_manifest(tmp_path, [row]), tmp_path)
    assert result["sampleCount"] == 1
    assert result["labelCounts"] == {"correct": 1}
    assert not result["dataStructureComplete"]
    assert not result["trainedModelCreated"]
    assert not result["qualityAssessmentValidated"]
    assert "binary_training_labels_incomplete" in result["structuralGaps"]
    assert all(frame["phase"] is None for frame in result["samples"][0]["frames"])
    assert (
        result["samples"][0]["frames"][0]["features"]["left.estimatedWorldAngleDeg"]
        is None
    )


def test_complete_structure_does_not_claim_accuracy_or_train_model(tmp_path):
    rows = [
        sample(tmp_path, "train-a"),
        sample(tmp_path, "train-b", label="needs_correction"),
        sample(tmp_path, "val", "validation"),
        sample(tmp_path, "test", "test"),
    ]
    result = prepare(write_manifest(tmp_path, rows), tmp_path)
    assert result["dataStructureComplete"] and result["structuralGaps"] == []
    assert (
        not result["trainedModelCreated"] and not result["qualityAssessmentValidated"]
    )
    assert "front_view_measurement_validation" in result["pendingRequirements"]


@pytest.mark.parametrize("field", ["participantId", "recordingId", "sourceVideoSha256"])
def test_same_person_recording_or_content_cannot_cross_splits(tmp_path, field):
    first = sample(tmp_path, "a")
    second = sample(tmp_path, "b", "test")
    if field == "sourceVideoSha256":
        data = observation("a")
        (tmp_path / "b.json").write_text(json.dumps(data))
    else:
        second[field] = first[field]
    with pytest.raises(ValueError, match="leakage"):
        prepare(write_manifest(tmp_path, [first, second]), tmp_path)


def test_source_file_cannot_escape_data_root(tmp_path):
    row = sample(tmp_path)
    row["observationsPath"] = "../outside.json"
    with pytest.raises(ValueError, match="outside"):
        prepare(write_manifest(tmp_path, [row]), tmp_path)


def test_metadata_whitespace_cannot_hide_participant_leakage(tmp_path):
    first = sample(tmp_path, "a")
    second = sample(tmp_path, "b", "test")
    second["participantId"] = "  a  "
    with pytest.raises(ValueError, match="leakage"):
        prepare(write_manifest(tmp_path, [first, second]), tmp_path)


@pytest.mark.parametrize(
    "fault", ["nan_angle", "negative_time", "unordered_frames", "empty_frames"]
)
def test_invalid_temporal_values_rejected(tmp_path, fault):
    row = sample(tmp_path)
    data = observation("demo")
    if fault == "nan_angle":
        data["frames"][0]["elbows"]["left"]["imageAngleDeg"] = float("nan")
    elif fault == "negative_time":
        data["frames"][0]["timeSeconds"] = -1
    elif fault == "unordered_frames":
        data["frames"].reverse()
    else:
        data["frames"] = []
    (tmp_path / "demo.json").write_text(json.dumps(data))
    with pytest.raises(ValueError):
        prepare(write_manifest(tmp_path, [row]), tmp_path)


def test_manual_phase_annotation_is_applied_without_guessing_gaps(tmp_path):
    row = sample(tmp_path)
    row["annotationsPath"] = "phases.json"
    (tmp_path / "phases.json").write_text(
        json.dumps([dict(phase="neutral_start", startSeconds=0, endSeconds=0.2)])
    )
    result = prepare(write_manifest(tmp_path, [row]), tmp_path)
    frames = result["samples"][0]["frames"]
    assert frames[0]["phase"] == "neutral_start" and frames[1]["phase"] is None


def test_inconsistent_extraction_versions_rejected(tmp_path):
    rows = [sample(tmp_path, "a"), sample(tmp_path, "b")]
    report = observation("b")
    report["versions"]["numpy"] = "different-extractor-version"
    (tmp_path / "b.json").write_text(json.dumps(report))
    with pytest.raises(ValueError, match="versions differ"):
        prepare(write_manifest(tmp_path, rows), tmp_path)


@pytest.mark.parametrize(
    "field,value",
    [
        ("cameraView", "side"),
        ("split", "evaluation"),
        ("label", "invented_label"),
        ("labelSource", "unlabeled"),
    ],
)
def test_unknown_or_contradictory_metadata_rejected(tmp_path, field, value):
    row = sample(tmp_path)
    row[field] = value
    with pytest.raises(ValueError):
        prepare(write_manifest(tmp_path, [row]), tmp_path)


def test_empty_manifest_is_explicitly_not_a_dataset(tmp_path):
    with pytest.raises(ValueError, match="kosong"):
        prepare(write_manifest(tmp_path, []), tmp_path)


def test_dataset_cli_preserves_existing_output(tmp_path, monkeypatch):
    from scripts.prepare_punch_dataset import main

    row = sample(tmp_path)
    manifest = write_manifest(tmp_path, [row])
    output = tmp_path / "features.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "prepare_punch_dataset",
            "--manifest",
            str(manifest),
            "--data-root",
            str(tmp_path),
            "--output",
            str(output),
        ],
    )
    main()
    before = output.read_bytes()
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2 and output.read_bytes() == before
