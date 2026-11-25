"""Read-time assessment of stored paired 2D observations, without model/DB I/O.

No inference, filenames, re-training, or private reference artifacts are needed.
The referenceValue paired by Coach comparison is the target for that recording.
"""

from math import ceil, hypot, isfinite
from statistics import median

from app.intelligence.posture_rubric import (
    DIRECTION_AGREEMENT,
    MIN_COVERAGE,
    MIN_EXCURSION,
    MIN_SAMPLES,
    RUBRICS,
    RUBRIC_VERSION,
    SIDE_DOMINANCE,
    TOLERANCES,
)


def number(value):
    return type(value) in (int, float) and isfinite(value)


def value(frame, name, column):
    item = frame.get("features", {}).get(name, {})
    unit = "deg" if name.endswith("_deg") else "torso_length_ratio"
    result = item.get(column)
    if item.get("unit") != unit or not number(result):
        return None
    if unit == "deg" and not 0 <= result <= 180:
        return None
    if unit != "deg" and abs(result) > 8:
        return None
    # tolerance_pending is about legacy colors, not missing geometry.
    if item.get("reason") not in (None, "tolerance_pending"):
        return None
    return result


def knees(frame, column):
    pair = [value(frame, side + "_knee_deg", column) for side in ("left", "right")]
    return sorted(pair) if all(v is not None for v in pair) else None


def xy(frame, side, limb, column):
    pair = [value(frame, f"{side}_{limb}_{axis}_torso", column) for axis in ("x", "y")]
    return pair if all(v is not None for v in pair) else None


def active_side(frames, limb, column):
    excursions = {}
    for side in ("left", "right"):
        points = [xy(f, side, limb, column) for f in frames]
        points = [p for p in points if p is not None]
        if (
            len(points) < MIN_SAMPLES
            or len(points) / max(1, len(frames)) < MIN_COVERAGE
        ):
            return None
        excursions[side] = hypot(
            *(max(p[a] for p in points) - min(p[a] for p in points) for a in (0, 1))
        )
    first, second = sorted(excursions, key=excursions.get, reverse=True)
    if (
        excursions[first] < MIN_EXCURSION
        or excursions[first] < SIDE_DOMINANCE * excursions[second]
    ):
        return None
    return first


def motion_window(frames, side, limb):
    points = [xy(f, side, limb, "referenceValue") for f in frames]
    initial = [p for p in points[: max(2, len(points) // 5)] if p is not None]
    if len(initial) < 2:
        return [], []
    base = [median(p[a] for p in initial) for a in (0, 1)]
    distances = [hypot(p[0] - base[0], p[1] - base[1]) if p else -1 for p in points]
    peak = max(range(len(points)), key=distances.__getitem__)
    if distances[peak] < MIN_EXCURSION:
        return [], []
    start = max(
        (
            i
            for i in range(peak)
            if 0 <= distances[i] <= max(0.10, distances[peak] * 0.15)
        ),
        default=0,
    )
    selected = list(range(start, peak + 1))
    # A very fast action is unassessable at this stored sampling resolution.
    if len(selected) < MIN_SAMPLES:
        return [], []
    return selected, list(range(max(start, peak - 3), peak + 1))


def formed_window(frames):
    observed = [(i, knees(f, "referenceValue")) for i, f in enumerate(frames)]
    bends = sorted(p[0] for _, p in observed if p)
    if len(bends) < MIN_SAMPLES or bends[0] > 165:
        return []
    # Select formed stance from Coach geometry, independent of user mistakes.
    threshold = min(bends[len(bends) // 4], bends[0] + 20)
    return [i for i, p in observed if p and p[0] <= threshold]


def camera_usable(frame, timeline, measurement, user_side):
    """Conservative observable projection checks, not a camera-pose classifier.

    Legacy paired features already passed extraction visibility filtering. When
    actual landmarks are stored, reject gaps, foreshortening and collapsed torso.
    """
    if timeline is None:
        return True
    rows = timeline.get("frames", [])
    if not rows or not number(frame.get("timeSeconds")):
        return False
    row = min(rows, key=lambda r: abs(r["timeSeconds"] - frame["timeSeconds"]))
    if abs(row["timeSeconds"] - frame["timeSeconds"]) > 0.15:
        return False
    width, height = timeline.get("imageWidth"), timeline.get("imageHeight")
    if not number(width) or not number(height) or min(width, height) <= 0:
        return False
    points = {
        p["index"]: (p["x"] * width / height, p["y"])
        for p in row.get("landmarks", [])
        if all(number(p.get(k)) for k in ("x", "y", "visibility"))
        and p["visibility"] >= 0.5
    }
    if not all(i in points for i in (11, 12, 23, 24)):
        return False

    def distance(a, b):
        return hypot(a[0] - b[0], a[1] - b[1])

    shoulder = tuple((points[11][a] + points[12][a]) / 2 for a in (0, 1))
    hip = tuple((points[23][a] + points[24][a]) / 2 for a in (0, 1))
    torso = distance(shoulder, hip)
    if torso < 1e-5:
        return False
    # Width/symmetry and 2D path grading require a non-collapsed frontal baseline.
    if (
        "path" in measurement
        or measurement in {"stance_width_torso", "knee_symmetry", "both_knees"}
    ) and distance(points[11], points[12]) / torso < 0.20:
        return False
    triples = []
    if "knee" in measurement:
        triples = (
            [(23, 25, 27), (24, 26, 28)]
            if not user_side
            else [(23, 25, 27) if user_side == "left" else (24, 26, 28)]
        )
    elif "elbow" in measurement and user_side:
        triples = [(11, 13, 15) if user_side == "left" else (12, 14, 16)]
    elif "hip" in measurement and user_side:
        triples = [(11, 23, 25) if user_side == "left" else (12, 24, 26)]
    return all(
        all(i in points for i in t)
        and all(
            distance(points[a], points[b]) / torso >= 0.08 for a, b in zip(t, t[1:])
        )
        for t in triples
    )


def scalar(frame, measurement, column, side):
    if measurement in {"bent_knee", "other_knee", "both_knees", "knee_symmetry"}:
        pair = knees(frame, column)
        if pair is None:
            return None
        return {
            "bent_knee": pair[0],
            "other_knee": pair[1],
            "both_knees": pair,
            "knee_symmetry": pair[1] - pair[0],
        }[measurement]
    if measurement.startswith("active_") or measurement.endswith("_change"):
        joint = measurement.removeprefix("active_").removesuffix("_change")
        return value(frame, f"{side}_{joint}_deg", column) if side else None
    return value(frame, measurement, column)


def score_aspect(spec, frames, indices, user_side, ref_side, timeline):
    empty = dict(
        id=spec.id,
        points=None,
        correctionCode=None,
        reason="insufficient_comparison_samples",
        unit=spec.unit,
    )
    if len(indices) < MIN_SAMPLES:
        return empty
    errors, signed = [], []
    baseline = None
    path_measurement = spec.measurement.endswith("_path")
    change = spec.measurement.endswith("_change")
    camera_rejected = False
    observed_rows = []
    for i in indices:
        f = frames[i]
        if not camera_usable(f, timeline, spec.measurement, user_side):
            camera_rejected = True
            continue
        if path_measurement:
            limb = spec.measurement.removesuffix("_path")
            a, b = (
                xy(f, user_side, limb, "value"),
                xy(f, ref_side, limb, "referenceValue"),
            )
            if a is not None and user_side != ref_side:
                a = [
                    -a[0],
                    a[1],
                ]  # Swap anatomical sides and mirror horizontal projection.
        else:
            a = scalar(f, spec.measurement, "value", user_side)
            b = scalar(f, spec.measurement, "referenceValue", ref_side)
        if a is None or b is None:
            continue
        observed_rows.append(f.get("referenceTimeSeconds"))
        if path_measurement or change:
            if baseline is None:
                baseline = (a, b)
            if path_measurement:
                # End-position grades absolute position; motion grades trajectory
                # relative to its start, preserving curvature and direction.
                aa, bb = a, b
                if spec.phase == "motion":
                    aa = [a[k] - baseline[0][k] for k in (0, 1)]
                    bb = [b[k] - baseline[1][k] for k in (0, 1)]
                dx, dy = aa[0] - bb[0], aa[1] - bb[1]
                errors.append(hypot(dx, dy))
                signed.append(dy if abs(dy) >= abs(dx) else 0.0)
            else:
                delta = (a - baseline[0]) - (b - baseline[1])
                errors.append(abs(delta))
                signed.append(delta)
        elif isinstance(a, list):
            differences = [x - y for x, y in zip(a, b)]
            errors.append(sum(abs(v) for v in differences) / len(differences))
            signed.append(
                median(differences) if differences[0] * differences[1] >= 0 else 0.0
            )
        else:
            errors.append(abs(a - b))
            signed.append(a - b)
    if len(errors) < MIN_SAMPLES or len(errors) / len(indices) < MIN_COVERAGE:
        return {
            **empty,
            "reason": "camera_or_pose_inadequate"
            if camera_rejected
            else "joint_not_observable",
        }
    if (
        (path_measurement or change)
        and spec.phase == "motion"
        and len(set(observed_rows)) < 3
    ):
        return {**empty, "reason": "reference_motion_not_observable"}
    deviation = median(errors)
    dead_band, step = TOLERANCES[spec.unit]
    points = max(0, 100 - 15 * ceil(max(0, deviation - dead_band) / step))
    correction = None
    direction = median(signed)
    agreement = sum(
        v > dead_band if direction > 0 else v < -dead_band for v in signed
    ) / len(signed)
    if (
        points < 100
        and spec.corrections
        and abs(direction) > dead_band
        and agreement >= DIRECTION_AGREEMENT
    ):
        correction = spec.corrections[1 if direction > 0 else 0]
    return {**empty, "points": points, "correctionCode": correction, "reason": None}


def assess_posture(comparison, timeline=None):
    """Pure, bounded read-time projection; never mutate persisted worker output."""
    specs = RUBRICS.get(comparison.get("movementId"), ())
    frames = comparison.get("frames", [])[:32]
    stance = comparison.get("movementId", "").startswith("kuda_kuda_")
    limb = (
        "ankle"
        if comparison.get("movementId", "").startswith("tendangan_")
        else "wrist"
    )
    user_side = ref_side = None
    formed, motion, peak = [], [], []
    reason = None
    if comparison.get("status") != "compared" or not frames:
        reason = "comparison_not_assessable"
    elif stance:
        formed = formed_window(frames)
        if not formed:
            reason = "formed_stance_not_observable"
    else:
        ref_side = active_side(frames, limb, "referenceValue")
        user_side = active_side(frames, limb, "value")
        if not ref_side or not user_side:
            reason = "active_side_unclear"
        else:
            motion, peak = motion_window(frames, ref_side, limb)
            if not motion:
                reason = "reference_motion_not_observable"
    aspects = []
    for spec in specs:
        if reason:
            aspect = dict(
                id=spec.id,
                points=None,
                correctionCode=None,
                reason=reason,
                unit=spec.unit,
            )
        else:
            aspect = score_aspect(
                spec,
                frames,
                {"formed": formed, "motion": motion, "peak": peak}[spec.phase],
                user_side,
                ref_side,
                timeline,
            )
        aspects.append(aspect)
    assessed = sum(a["points"] is not None for a in aspects)
    ready = bool(specs) and all(
        a["points"] is not None for spec, a in zip(specs, aspects) if spec.primary
    )
    return dict(
        status="assessed" if ready else "partial" if assessed else "not_assessable",
        points=round(
            sum(a["points"] for a in aspects if a["points"] is not None) / assessed, 2
        )
        if ready and assessed
        else None,
        maxPoints=100,
        reason=None if ready else reason or "required_aspect_unavailable",
        aspects=aspects,
        rubricVersion=RUBRIC_VERSION,
    )
