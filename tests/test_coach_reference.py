"""Synthetic correctness fixtures test mechanics, not accuracy on real beginners."""

import copy
import csv
import hashlib
import json

import numpy as np
import pytest

from app.intelligence.coach_reference import FIELDS, compare, evaluate, fit, prepare
from app.intelligence.movement_catalog import MOVEMENTS
from app.intelligence.movement_features import (
    FAMILY_FEATURES,
    FEATURE_NAMES,
    FEATURE_VERSION,
)
from app.intelligence.reference_alignment import align


def report(identity, coach=0):
    signature = {
        "featureVersion": FEATURE_VERSION,
        "poseModelSha256": "a" * 64,
        "sampleFpsRequested": 15,
        "visibilityThreshold": 0.5,
        "maximumImageDimension": 1280,
        "cameraView": "front_fixed_as_input_assumption",
        "versions": {
            "numpy": "fixture",
            "mediapipe": "fixture",
            "opencv-contrib-python": "fixture",
        },
    }
    frames = []
    for i in range(32):
        features = {
            name: (100 + 4 * np.sin(i / 5) + coach * 0.4 * np.sin(i * 0.7))
            if name.endswith("_deg")
            else 0.5 + 0.1 * np.sin(i / 5) + coach * 0.01 * np.sin(i * 0.7)
            for name in FEATURE_NAMES
        }
        frames.append(
            {
                "frameIndex": i,
                "timeSeconds": i / 16,
                "features": features,
                "unavailableReasons": dict.fromkeys(FEATURE_NAMES),
            }
        )
    return {
        "schemaVersion": 1,
        "featureVersion": FEATURE_VERSION,
        "sourceVideoSha256": hashlib.sha256(identity.encode()).hexdigest(),
        "poseModelSha256": "a" * 64,
        "cameraView": signature["cameraView"],
        "extractionSignature": signature,
        "video": {"durationSeconds": 2, "decodedFrameCount": 32},
        "frames": frames,
    }


def sample(identity, coach=0, movement="pukulan_depan", split="train"):
    return {
        "sampleId": identity,
        "participantId": f"coach-{coach}",
        "recordingId": identity,
        "split": split,
        "movementId": movement,
        "referenceSource": "user_confirmed_coach_demo",
        "referenceIsCorrect": True,
        "manualPhases": None,
        "observations": report(identity, coach),
    }


def dataset(samples):
    return {"datasetType": "correct-coach-reference-v1", "samples": samples}


@pytest.fixture
def references():
    return dataset([sample("reference-" + str(i), i) for i in range(3)])


def test_single_confirmed_coach_is_accepted_without_making_up_tolerances():
    reference = sample("reference")
    model = fit(dataset([reference]))
    result = compare(
        json.loads(json.dumps(model, allow_nan=False)),
        reference["observations"],
        "pukulan_depan",
    )
    assert result["status"] == "compared" and result["isReferenceReplay"]
    assert result["toleranceStatus"] == "insufficient_independent_coaches"
    assert all(f["maximumDeviation"] == 0 for f in result["features"].values())
    assert all(
        item["color"] is None
        for f in result["frames"]
        for item in f["features"].values()
    )
    assert result["correctness"] is None and result["score"] is None


@pytest.mark.parametrize("movement", sorted(MOVEMENTS))
def test_every_movement_uses_its_own_body_features(movement):
    s = sample("reference", movement=movement)
    model = fit(dataset([s]))
    assert model["profiles"][movement]["featureNames"] == list(
        FAMILY_FEATURES[MOVEMENTS[movement][0]]
    )
    assert compare(model, s["observations"], movement)["status"] == "compared"


def test_temporal_alignment_handles_local_speed_changes():
    names = list(FAMILY_FEATURES["pukulan"])
    ref = np.zeros((32, len(names)))
    ref[8:16] = np.arange(8)[:, None]
    ref[16:24] = np.arange(8)[::-1, None]
    user = np.vstack((np.zeros((3, len(names))), ref[:-3]))
    result = align(user, ref, names)
    assert np.max(result["deviations"]) == 0
    assert np.mean(abs(user - ref)) > 0
    assert all(abs(i - j) <= 6 for i, j in enumerate(result["referenceBins"]))


def test_changed_elbow_is_localized_with_directional_feedback(references):
    model = fit(references)
    assert (
        model["profiles"]["pukulan_depan"]["tolerances"]["left_elbow_deg"] is not None
    )
    user = report("beginner", 1)
    for frame in user["frames"]:
        frame["features"]["left_elbow_deg"] -= 30
    result = compare(model, user, "pukulan_depan")
    changed = [f["joints"]["left_elbow"] for f in result["frames"]]
    assert all(j["color"] == "red" for j in changed)
    assert all(j["feedbackCode"] == "lebih_menekuk_dari_referensi" for j in changed)
    assert result["features"]["right_elbow_deg"]["maximumDeviation"] < 2
    assert (
        result["correctness"] is None
    )  # Experimental deviation, not a validated verdict.


def test_all_three_colors_follow_learned_variation(references):
    model = fit(references)
    user = report("user", 1)
    baseline = compare(model, user, "pukulan_depan")
    threshold = model["profiles"]["pukulan_depan"]["tolerances"]["left_elbow_deg"]
    for delta, color in [
        (0, "green"),
        ((threshold["yellowAbove"] + threshold["redAbove"]) / 2, "yellow"),
        (threshold["redAbove"] + 5, "red"),
    ]:
        # Constant matching fixture holds alignment fixed while exercising exact boundaries.
        item = copy.deepcopy(user)
        for i, frame in enumerate(item["frames"]):
            frame["features"]["left_elbow_deg"] = (
                baseline["frames"][i]["features"]["left_elbow_deg"]["referenceValue"]
                + delta
            )
        compared = compare(model, item, "pukulan_depan")
        assert any(
            f["joints"]["left_elbow"]["color"] == color for f in compared["frames"]
        )


def test_hidden_elbow_never_becomes_green_or_gets_filled(references):
    model = fit(references)
    user = report("user")
    for frame in user["frames"]:
        frame["features"]["left_elbow_deg"] = None
        frame["unavailableReasons"]["left_elbow_deg"] = "low_visibility"
    result = compare(model, user, "pukulan_depan")
    assert result["status"] == "compared"
    assert result["features"]["left_elbow_deg"]["sampleCount"] == 0
    assert all(
        f["joints"]["left_elbow"]["color"] is None
        and f["joints"]["left_elbow"]["deviation"] is None
        for f in result["frames"]
    )


def test_unobservable_sequence_returns_unassessable(references):
    model = fit(references)
    user = report("user")
    for frame in user["frames"]:
        frame["features"] = dict.fromkeys(FEATURE_NAMES)
        frame["unavailableReasons"] = dict.fromkeys(FEATURE_NAMES, "pose_unavailable")
    result = compare(model, user, "pukulan_depan")
    assert result["status"] == "not_assessable" and result["frames"] == []


def test_annotations_transfer_only_when_actually_supplied():
    s = sample("reference")
    s["manualPhases"] = [{"phase": "execution", "startSeconds": 0.5, "endSeconds": 1.5}]
    result = compare(fit(dataset([s])), s["observations"], "pukulan_depan")
    assert result["semanticPhasesAvailable"]
    assert result["frames"][16]["phase"] == "execution"
    s["manualPhases"] = None
    result = compare(fit(dataset([s])), s["observations"], "pukulan_depan")
    assert all(f["phase"] is None for f in result["frames"])


def test_heldout_data_never_changes_reference_or_color_bounds(references):
    original = fit(references)
    references["samples"].append(sample("validation", 20, split="validation"))
    model = fit(references)
    assert model["profiles"] == original["profiles"]
    assessment = evaluate(model, references, "validation")
    assert assessment["sampleCount"] == 1
    assert assessment["correctnessAccuracy"] is None
    assert evaluate(model, references, "test")["sampleCount"] == 0


@pytest.mark.parametrize(
    "kind",
    ["incorrect", "source", "participant", "recording", "video", "id", "signature"],
)
def test_bad_reference_metadata_is_rejected(kind, references):
    a = references["samples"][0]
    b = sample("validation", 4, split="validation")
    references["samples"].append(b)
    if kind == "incorrect":
        a["referenceIsCorrect"] = False
    elif kind == "source":
        a["referenceSource"] = "unlabeled"
    elif kind in {"participant", "recording"}:
        b[kind + "Id"] = a[kind + "Id"]
    elif kind == "video":
        b["observations"]["sourceVideoSha256"] = a["observations"]["sourceVideoSha256"]
    elif kind == "id":
        b["sampleId"] = a["sampleId"]
    else:
        b["observations"]["extractionSignature"]["sampleFpsRequested"] = 10
    with pytest.raises(ValueError):
        fit(references)


def test_evaluation_independently_rejects_coach_overlap(references):
    model = fit(references)
    separate = dataset([sample("heldout", 0, split="test")])
    with pytest.raises(ValueError, match="overlaps"):
        evaluate(model, separate, "test")


def test_more_videos_from_one_coach_do_not_imply_population_variation():
    refs = dataset([sample("video" + str(i), 0) for i in range(5)])
    profile = fit(refs)["profiles"]["pukulan_depan"]
    assert profile["coachCount"] == 1
    assert all(v is None for v in profile["tolerances"].values())


def test_manifest_accepts_existing_coach_as_correct_without_extra_review(tmp_path):
    (tmp_path / "coach.json").write_text(json.dumps(report("coach")), encoding="utf-8")
    manifest = tmp_path / "references.csv"
    with manifest.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerow(
            dict(
                zip(
                    FIELDS,
                    [
                        "one",
                        "coach",
                        "recording",
                        "train",
                        "pukulan_depan",
                        "user_confirmed_coach_demo",
                        "coach.json",
                        "",
                    ],
                )
            )
        )
    prepared = prepare(manifest, tmp_path)
    assert prepared["samples"][0]["referenceIsCorrect"] is True
    assert fit(prepared)["profiles"]["pukulan_depan"]["coachCount"] == 1
    manifest.write_text(manifest.read_text().replace("coach.json", "../escape.json"))
    with pytest.raises(ValueError):
        prepare(manifest, tmp_path)


@pytest.mark.parametrize(
    "kind", ["version", "movement", "dimensions", "threshold", "config"]
)
def test_incompatible_reference_artifacts_fail_closed(kind, references):
    model = fit(references)
    user = report("user")
    movement = "pukulan_depan"
    if kind == "version":
        model["featureVersion"] = "other"
    elif kind == "movement":
        movement = "invented"
    elif kind == "dimensions":
        model["profiles"][movement]["templates"][0]["sequence"] = [[0]]
    elif kind == "threshold":
        model["profiles"][movement]["tolerances"]["left_elbow_deg"]["redAbove"] = -1
    else:
        user["extractionSignature"]["sampleFpsRequested"] = 10
    with pytest.raises(ValueError):
        compare(model, user, movement)
