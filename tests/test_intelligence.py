import numpy as np
import pytest
from app.intelligence.contracts import Pose, FEATURE_VERSION
from app.intelligence.features.biomechanics import angle, BiomechanicalFeatures
from app.intelligence.preprocessing.landmarks import VisibleLandmarkPreprocessor
from app.intelligence.evaluators.reference import RobustReferenceEvaluator
from app.services.analysis import EvaluationService


def test_angles():
    assert angle([1, 0], [0, 0], [0, 1]) == pytest.approx(90)
    assert angle([-1, 0], [0, 0], [1, 0]) == pytest.approx(180)
    assert angle([0, 0], [0, 0], [1, 0]) is None
    assert angle([np.nan, 0], [0, 0], [1, 0]) is None


def test_normalization_invariant():
    rng = np.random.default_rng(3)
    p = rng.random((33, 4))
    p[:, 3] = 1
    other = p.copy()
    other[:, :3] = other[:, :3] * 4 + 7
    pre = VisibleLandmarkPreprocessor()
    assert np.allclose(pre.normalize(Pose(p)), pre.normalize(Pose(other)))
    p[11, 3] = 0
    assert pre.normalize(Pose(p)) is None


def test_visibility_omits_features():
    p = np.random.default_rng(1).random((33, 4))
    p[:, 3] = 1
    p[13, 3] = 0
    result = BiomechanicalFeatures().extract(
        VisibleLandmarkPreprocessor().normalize(Pose(p))
    )
    assert "left_elbow_angle" not in result
    assert "right_elbow_angle" in result


def test_evaluator_relative_and_no_zero_iqr():
    profile = {
        "feature_version": FEATURE_VERSION,
        "feature_statistics": {str(i): {"median": 10, "iqr": 2} for i in range(8)},
    }
    evaluator = RobustReferenceEvaluator()
    assert evaluator.compare({str(i): 10 for i in range(8)}, profile)["score"] == 100
    assert evaluator.compare({str(i): 12 for i in range(8)}, profile)["score"] == 50
    assert evaluator.compare({"0": 12}, profile) is None
    for s in profile["feature_statistics"].values():
        s["iqr"] = 0
    assert evaluator.compare({str(i): 12 for i in range(8)}, profile) is None


def test_missing_reference_still_extracts_pose_and_closes():
    class Extractor:
        closed = False

        def extract(self, rgb):
            return None

        def close(self):
            self.closed = True

    extractor = Extractor()
    service = EvaluationService(
        extractor_factory=lambda: extractor, frame_source=lambda *args: [(0, 0, None)]
    )
    result = service.analyze(None, "pukulan", [])
    assert result["status"] == "reference_not_ready" and result["score"] is None
    assert result["analysis"]["frames_processed"] == 1
    assert extractor.closed
