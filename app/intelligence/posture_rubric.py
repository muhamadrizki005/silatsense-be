"""Versioned experimental policy, not IPSI thresholds or clinical measurements."""

from dataclasses import dataclass

RUBRIC_VERSION = "posture-reference-v1"
# Independent scales: never add degrees to torso-length ratios.
TOLERANCES = {
    "deg": (20.0, 30.0),  # dead band, additional deviation per 15-point deduction
    "torso_length_ratio": (0.20, 0.30),
}
MIN_SAMPLES = 4
MIN_COVERAGE = 0.60
DIRECTION_AGREEMENT = 0.75
MIN_EXCURSION = 0.20
SIDE_DOMINANCE = 1.25


@dataclass(frozen=True)
class Aspect:
    id: str
    measurement: str
    unit: str = "deg"
    phase: str = "formed"
    corrections: tuple[str, str] | None = None  # negative, positive signed delta
    primary: bool = True


def angle(id, measurement, phase="formed", corrections=None):
    return Aspect(id, measurement, phase=phase, corrections=corrections)


def path(id, limb, phase="motion", corrections=None):
    return Aspect(id, limb + "_path", "torso_length_ratio", phase, corrections)


BEND = ("knee_bend_excessive", "knee_bend_insufficient")
ELBOW = ("elbow_bend_excessive", "elbow_bend_insufficient")
LEAN = ("torso_lean_insufficient", "torso_lean_excessive")
RUBRICS = {
    "kuda_kuda_tengah": (
        angle("knees_bend", "both_knees", corrections=BEND),
        angle(
            "knee_symmetry",
            "knee_symmetry",
            corrections=(
                "knee_asymmetry_less_than_reference",
                "knee_asymmetry_excessive",
            ),
        ),
        Aspect(
            "stance_width",
            "stance_width_torso",
            "torso_length_ratio",
            corrections=("stance_too_narrow", "stance_too_wide"),
        ),
    ),
    "kuda_kuda_depan": (
        angle("front_knee_bend", "bent_knee", corrections=BEND),
        angle(
            "rear_leg_extension",
            "other_knee",
            corrections=(
                "rear_leg_extension_insufficient",
                "rear_leg_extension_excessive",
            ),
        ),
        angle("torso_inclination", "torso_inclination_deg", corrections=LEAN),
    ),
    "kuda_kuda_samping": (
        angle("bent_knee", "bent_knee", corrections=BEND),
        angle(
            "other_leg_extension",
            "other_knee",
            corrections=(
                "other_leg_extension_insufficient",
                "other_leg_extension_excessive",
            ),
        ),
        Aspect(
            "stance_width",
            "stance_width_torso",
            "torso_length_ratio",
            corrections=("stance_too_narrow", "stance_too_wide"),
        ),
    ),
    "pukulan_depan": (
        angle(
            "elbow_extension",
            "active_elbow",
            "peak",
            ("elbow_extension_insufficient", "elbow_extension_excessive"),
        ),
        path("wrist_path", "wrist"),
    ),
    "pukulan_melingkar": (
        path("curved_wrist_path", "wrist"),
        angle("elbow_change", "elbow_change", "motion"),
    ),
    "pukulan_bandul": (
        path(
            "upward_wrist_path",
            "wrist",
            corrections=("wrist_raise_excessive", "wrist_raise_insufficient"),
        ),
        angle("elbow_change", "elbow_change", "motion"),
    ),
    "tendangan_depan": (
        angle("knee_change", "knee_change", "motion"),
        path("ankle_path", "ankle"),
        angle("torso_inclination", "torso_inclination_deg", "peak", LEAN),
    ),
    "tendangan_sabit": (
        path("swing_ankle_path", "ankle"),
        angle("knee_change", "knee_change", "motion"),
        angle("hip_change", "hip_change", "motion"),
    ),
    "tendangan_t": (
        path("lateral_leg_position", "ankle", "peak"),
        angle(
            "knee_extension",
            "active_knee",
            "peak",
            ("knee_extension_insufficient", "knee_extension_excessive"),
        ),
        angle("torso_inclination", "torso_inclination_deg", "peak", LEAN),
    ),
    "tangkisan_atas": (
        path(
            "upward_wrist_path",
            "wrist",
            corrections=("wrist_raise_excessive", "wrist_raise_insufficient"),
        ),
        path(
            "wrist_end_position",
            "wrist",
            "peak",
            ("wrist_position_too_high", "wrist_position_too_low"),
        ),
        angle("elbow_bend", "active_elbow", "peak", ELBOW),
    ),
    "tangkisan_dalam": (
        path("inward_wrist_path", "wrist"),
        angle("elbow_bend", "active_elbow", "peak", ELBOW),
    ),
    "tangkisan_bawah": (
        path(
            "downward_wrist_path",
            "wrist",
            corrections=("wrist_lower_insufficient", "wrist_lower_excessive"),
        ),
        path(
            "wrist_end_position",
            "wrist",
            "peak",
            ("wrist_position_too_high", "wrist_position_too_low"),
        ),
        angle("elbow_bend", "active_elbow", "peak", ELBOW),
    ),
}
