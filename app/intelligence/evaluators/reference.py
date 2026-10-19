import numpy as np
from app.intelligence.contracts import FEATURE_VERSION


class RobustReferenceEvaluator:
    """Relative dataset similarity, never an official correctness metric."""

    def compare(self, features: dict[str, float], profile: dict) -> dict | None:
        if profile.get("feature_version") != FEATURE_VERSION:
            return None
        statistics = profile.get("feature_statistics", {})
        usable = {k: s for k, s in statistics.items() if s.get("iqr", 0) > 1e-6}
        shared = sorted(set(usable) & set(features))
        if len(shared) < 8 or len(shared) < len(usable) * 0.7:
            return None
        deviations = []
        for key in shared:
            stats = usable[key]
            delta = features[key] - stats["median"]
            deviations.append(
                {
                    "feature": key,
                    "deviation": float(delta),
                    "distance": float(abs(delta) / stats["iqr"]),
                    "observed": features[key],
                    "reference_median": stats["median"],
                }
            )
        distance = float(np.mean([min(d["distance"], 10) for d in deviations]))
        return {
            "distance": distance,
            "score": round(100 / (1 + distance), 1),
            "deviations": deviations,
            "features_compared": len(shared),
        }
