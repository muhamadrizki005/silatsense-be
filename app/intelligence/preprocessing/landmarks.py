import numpy as np
from app.intelligence.contracts import Pose


class VisibleLandmarkPreprocessor:
    def __init__(self, visibility: float = 0.5):
        self.visibility = visibility

    def normalize(self, pose: Pose) -> np.ndarray | None:
        p = np.array(pose.landmarks, dtype=float, copy=True)
        if p.shape != (33, 4):
            return None
        p[(p[:, 3] < self.visibility) | ~np.isfinite(p).all(axis=1), :3] = np.nan
        if not np.isfinite(p[[11, 12, 23, 24], :3]).all():
            return None
        origin = (p[23, :3] + p[24, :3]) / 2
        scale = np.linalg.norm(p[11, :2] - p[12, :2])
        if scale < 1e-6:
            return None
        p[:, :3] = (p[:, :3] - origin) / scale
        return p
