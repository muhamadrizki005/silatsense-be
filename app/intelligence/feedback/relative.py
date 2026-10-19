LABELS = {
    "elbow": "siku",
    "shoulder": "bahu",
    "hip": "pinggul",
    "knee": "lutut",
    "wrist": "pergelangan tangan",
    "ankle": "pergelangan kaki",
    "torso": "batang tubuh",
    "stance": "lebar kuda-kuda",
}


class RelativeFeedback:
    def generate(self, deviations: list[dict]) -> list[dict]:
        issues = []
        for d in sorted(deviations, key=lambda x: x["distance"], reverse=True):
            if d["distance"] < 1:
                continue
            feature = d["feature"]
            side = (
                " kiri"
                if feature.startswith("left_")
                else " kanan"
                if feature.startswith("right_")
                else ""
            )
            part = next((key for key in LABELS if key in feature), "torso")
            issues.append(
                {
                    "body_part": (
                        "left_" if side == " kiri" else "right_" if side else ""
                    )
                    + part,
                    "feature": feature,
                    "deviation": round(d["deviation"], 3),
                    "severity": "high"
                    if d["distance"] >= 3
                    else "medium"
                    if d["distance"] >= 2
                    else "low",
                    "feedback": f"Posisi {LABELS[part]}{side} berbeda dari gerakan referensi.",
                }
            )
        return issues[:6]
