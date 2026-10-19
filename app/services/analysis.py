from pathlib import Path
from app.core.config import settings
from app.intelligence.contracts import ANALYZER_VERSION, FEATURE_VERSION
from app.intelligence.features.presentation import measurements, raw_pose
from app.intelligence.pose.mediapipe_extractor import MediaPipePoseExtractor
from app.intelligence.preprocessing.landmarks import VisibleLandmarkPreprocessor
from app.intelligence.features.biomechanics import BiomechanicalFeatures
from app.intelligence.evaluators.reference import RobustReferenceEvaluator
from app.intelligence.feedback.relative import RelativeFeedback
from app.intelligence.classifiers.noop import NoClassifier
from app.services.video import sampled_frames


class EvaluationService:
    def __init__(
        self,
        extractor_factory=None,
        preprocessor=None,
        features=None,
        classifier=None,
        evaluator=None,
        feedback=None,
        frame_source=None,
    ):
        self.extractor_factory = extractor_factory or (
            lambda: MediaPipePoseExtractor(settings.pose_model_path)
        )
        self.preprocessor = preprocessor or VisibleLandmarkPreprocessor()
        self.features = features or BiomechanicalFeatures()
        self.classifier = classifier or NoClassifier()
        self.evaluator = evaluator or RobustReferenceEvaluator()
        self.feedback = feedback or RelativeFeedback()
        self.frame_source = frame_source or sampled_frames

    def analyze(self, path: Path, movement: str, profiles: list[dict]) -> dict:
        result = {
            "movement": movement,
            "matched_variant": None,
            "reference_profile_id": None,
            "score": None,
            "status": "reference_not_ready",
            "pose_status": "not_detected",
            "analysis": {
                "frames_processed": 0,
                "valid_pose_frames": 0,
                "key_frame": None,
                "key_frame_time": None,
                "method": "static-reference-pose",
            },
            "issues": [],
            "model": {"analyzer_version": ANALYZER_VERSION, "feature_version": FEATURE_VERSION, "reference_version": None},
            "pose": None,
            "measurements": [],
        }
        best = None
        fallback = None
        extractor = self.extractor_factory()
        try:
            for index, seconds, rgb in self.frame_source(
                path, settings.sample_fps, settings.max_video_seconds
            ):
                result["analysis"]["frames_processed"] += 1
                pose = extractor.extract(rgb)
                normalized = self.preprocessor.normalize(pose) if pose else None
                if normalized is None:
                    continue
                features = self.features.extract(normalized)
                if len(features) < 8:
                    continue
                result["analysis"]["valid_pose_frames"] += 1
                if fallback is None:
                    fallback = (features, raw_pose(pose, rgb, index, seconds), index, seconds)
                predicted = self.classifier.predict(features, movement)
                for profile in profiles:
                    if predicted and profile["variant"] != predicted:
                        continue
                    comparison = self.evaluator.compare(features, profile)
                    if comparison and (
                        best is None or comparison["distance"] < best[0]["distance"]
                    ):
                        best = (comparison, profile, index, seconds, features,
                                raw_pose(pose, rgb, index, seconds))
        finally:
            extractor.close()
        if result["analysis"]["valid_pose_frames"]:
            result["pose_status"] = "detected"
        if fallback:
            features, pose_data, index, seconds = fallback
            result["pose"] = pose_data
            result["measurements"] = measurements(features)
            result["analysis"].update(key_frame=index, key_frame_time=seconds)
        if not profiles:
            return result
        if result["pose_status"] == "not_detected":
            result["status"] = "insufficient_pose"
        elif best is None:
            result["status"] = "insufficient_features"
        else:
            comparison, profile, index, seconds, features, pose_data = best
            result["pose"] = pose_data
            result["measurements"] = measurements(features, profile,
                {d["feature"] for d in comparison["deviations"]})
            result.update(
                status="experimental",
                score=comparison["score"],
                matched_variant=profile["variant"],
                reference_profile_id=profile.get("id"),
                issues=self.feedback.generate(comparison["deviations"]),
            )
            result["analysis"].update(
                key_frame=index,
                key_frame_time=seconds,
                features_compared=comparison["features_compared"],
            )
            result["model"]["reference_version"] = profile["version"]
        return result
