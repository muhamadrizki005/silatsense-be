import numpy as np


def angle(a, b, c) -> float | None:
    a, b, c = (np.asarray(v, dtype=float)[:2] for v in (a, b, c))
    u, v = a - b, c - b
    denominator = np.linalg.norm(u) * np.linalg.norm(v)
    if not np.isfinite(denominator) or denominator < 1e-8:
        return None
    return float(np.degrees(np.arccos(np.clip(np.dot(u, v) / denominator, -1, 1))))


class BiomechanicalFeatures:
    def extract(self, p: np.ndarray) -> dict[str, float]:
        features = {}
        for side, shoulder, elbow, wrist, hip, knee, ankle in (
            ("left", 11, 13, 15, 23, 25, 27),
            ("right", 12, 14, 16, 24, 26, 28),
        ):
            for joint, triple in {
                "elbow": (shoulder, elbow, wrist),
                "shoulder": (elbow, shoulder, hip),
                "hip": (shoulder, hip, knee),
                "knee": (hip, knee, ankle),
            }.items():
                value = angle(*(p[i] for i in triple))
                if value is not None:
                    features[f"{side}_{joint}_angle"] = value
            for name, start, end in [
                ("wrist_relative_to_shoulder", shoulder, wrist),
                ("ankle_relative_to_hip", hip, ankle),
            ]:
                for axis, idx in [("x", 0), ("y", 1)]:
                    value = p[end, idx] - p[start, idx]
                    if np.isfinite(value):
                        features[f"{side}_{name}_{axis}"] = float(value)
        torso = (p[11, :2] + p[12, :2] - p[23, :2] - p[24, :2]) / 2
        if np.isfinite(torso).all() and np.linalg.norm(torso) > 1e-8:
            features["torso_inclination"] = float(
                np.degrees(np.arctan2(abs(torso[0]), -torso[1]))
            )
        for name, left, right in [
            ("shoulder_alignment", 11, 12),
            ("hip_alignment", 23, 24),
        ]:
            delta = p[right, :2] - p[left, :2]
            if np.isfinite(delta).all():
                features[name] = float(
                    np.degrees(np.arctan2(abs(delta[1]), abs(delta[0])))
                )
        if np.isfinite(p[[27, 28], :2]).all():
            features["stance_width_ratio"] = float(
                np.linalg.norm(p[27, :2] - p[28, :2])
            )
        return features
