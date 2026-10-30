"""Observable 2D projections, with explicit missing values; no grading thresholds."""

import numpy as np

from app.intelligence.features.biomechanics import angle

FEATURE_VERSION = "movement-image-features-v1"
TRIPLES = {
    f"{side}_{joint}_deg": triple
    for side, s, e, w, h, k, a in (
        ("left", 11, 13, 15, 23, 25, 27),
        ("right", 12, 14, 16, 24, 26, 28),
    )
    for joint, triple in {
        "elbow": (s, e, w),
        "shoulder": (e, s, h),
        "hip": (s, h, k),
        "knee": (h, k, a),
    }.items()
}
RELATIVE = {
    f"{side}_{joint}": (origin, endpoint)
    for side, s, w, h, a in (("left", 11, 15, 23, 27), ("right", 12, 16, 24, 28))
    for joint, origin, endpoint in (("wrist", s, w), ("ankle", h, a))
}
FEATURE_NAMES = (
    tuple(TRIPLES)
    + tuple(f"{name}_{axis}_torso" for name in RELATIVE for axis in ("x", "y"))
    + ("stance_width_torso", "torso_inclination_deg")
)
FEATURE_UNITS = {
    name: "deg" if name.endswith("_deg") else "torso_length_ratio"
    for name in FEATURE_NAMES
}
FAMILY_FEATURES = {
    "pukulan": tuple(
        n
        for n in FEATURE_NAMES
        if any(v in n for v in ("elbow", "shoulder", "wrist", "torso_inclination"))
    ),
    "tangkisan": tuple(
        n
        for n in FEATURE_NAMES
        if any(v in n for v in ("elbow", "shoulder", "wrist", "torso_inclination"))
    ),
    "tendangan": tuple(
        n
        for n in FEATURE_NAMES
        if any(v in n for v in ("hip", "knee", "ankle", "torso_inclination"))
    ),
    "kuda_kuda": tuple(
        n
        for n in FEATURE_NAMES
        if any(v in n for v in ("hip", "knee", "ankle", "stance", "torso_inclination"))
    ),
}


def extract_features(landmarks, visibility=0.5):
    """Input follows runtime Pose: aspect-corrected x/y/z and visibility."""
    if not np.isfinite(visibility) or not 0 <= visibility <= 1:
        raise ValueError("Invalid visibility threshold")
    values = dict.fromkeys(FEATURE_NAMES)
    reasons = dict.fromkeys(FEATURE_NAMES, "pose_unavailable")
    if landmarks is None:
        return {"values": values, "unavailableReasons": reasons}
    p = np.asarray(landmarks, dtype=float)
    if p.shape != (33, 4):
        raise ValueError("Expected 33 aspect-corrected landmarks")

    def usable(indices):
        rows = p[list(indices)]
        return bool(
            np.isfinite(rows[:, [0, 1, 3]]).all() and (rows[:, 3] >= visibility).all()
        )

    def put(name, value, reason="low_visibility_or_invalid_landmark"):
        values[name] = (
            float(value) if value is not None and np.isfinite(value) else None
        )
        reasons[name] = None if values[name] is not None else reason

    for name, indices in TRIPLES.items():
        put(
            name,
            angle(*(p[i] for i in indices)) if usable(indices) else None,
            "low_visibility_or_degenerate_projection",
        )
    torso = None
    if usable((11, 12, 23, 24)):
        torso = (p[11, :2] + p[12, :2] - p[23, :2] - p[24, :2]) / 2
    scale = float(np.linalg.norm(torso)) if torso is not None else 0
    for name, (origin, endpoint) in RELATIVE.items():
        for axis, i in (("x", 0), ("y", 1)):
            value = (
                (p[endpoint, i] - p[origin, i]) / scale
                if scale > 1e-8 and usable((origin, endpoint))
                else None
            )
            put(f"{name}_{axis}_torso", value, "low_visibility_or_invalid_torso_scale")
    put(
        "stance_width_torso",
        np.linalg.norm(p[27, :2] - p[28, :2]) / scale
        if scale > 1e-8 and usable((27, 28))
        else None,
        "low_visibility_or_invalid_torso_scale",
    )
    put(
        "torso_inclination_deg",
        np.degrees(np.arctan2(abs(torso[0]), -torso[1])) if scale > 1e-8 else None,
        "low_visibility_or_invalid_torso_scale",
    )
    return {"values": values, "unavailableReasons": reasons}
