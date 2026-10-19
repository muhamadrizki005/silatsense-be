from dataclasses import dataclass
from typing import Protocol
import numpy as np

ANALYZER_VERSION = "prototype-v1"
FEATURE_VERSION = "image-plane-v1"


@dataclass
class Pose:
    landmarks: np.ndarray  # 33 x 4: aspect-corrected x, y, z, visibility


class PoseExtractor(Protocol):
    def extract(self, rgb: np.ndarray) -> Pose | None: ...
    def close(self) -> None: ...


class LandmarkPreprocessor(Protocol):
    def normalize(self, pose: Pose) -> np.ndarray | None: ...


class FeatureExtractor(Protocol):
    def extract(self, landmarks: np.ndarray) -> dict[str, float]: ...


class MovementClassifier(Protocol):
    def predict(self, features: dict[str, float], movement: str) -> str | None: ...


class MovementEvaluator(Protocol):
    def compare(self, features: dict[str, float], profile: dict) -> dict | None: ...


class FeedbackGenerator(Protocol):
    def generate(self, deviations: list[dict]) -> list[dict]: ...
