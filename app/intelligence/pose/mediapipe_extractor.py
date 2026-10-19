from pathlib import Path
import numpy as np
from app.intelligence.contracts import Pose


class MediaPipePoseExtractor:
    """Independent image inference avoids introducing artificial temporal assumptions."""

    def __init__(self, model_path: str):
        if not Path(model_path).is_file():
            raise FileNotFoundError(
                "Pose model is not installed. Run scripts.download_pose_model."
            )
        import mediapipe as mp

        self.mp = mp
        self.detector = mp.tasks.vision.PoseLandmarker.create_from_options(
            mp.tasks.vision.PoseLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=model_path),
                running_mode=mp.tasks.vision.RunningMode.IMAGE,
                num_poses=2,
            )
        )

    def extract(self, rgb: np.ndarray) -> Pose | None:
        result = self.detector.detect(
            self.mp.Image(
                image_format=self.mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb)
            )
        )
        if len(result.pose_landmarks) != 1:
            return None  # Never silently select another person's pose.
        h, w = rgb.shape[:2]
        return Pose(
            np.array(
                [
                    [p.x * w / h, p.y, p.z * w / h, p.visibility]
                    for p in result.pose_landmarks[0]
                ],
                dtype=float,
            )
        )

    def close(self):
        self.detector.close()
