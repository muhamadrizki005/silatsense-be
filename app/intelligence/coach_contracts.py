"""Lightweight identifiers shared by API configuration and inference."""

from typing import Literal

ANALYZER_VERSION = "coach-reference-dtw-v1"
FEATURE_VERSION = "movement-image-features-v1"
METHOD = "coach-reference-dtw"

MovementId = Literal[
    "pukulan_depan",
    "pukulan_melingkar",
    "pukulan_bandul",
    "tendangan_depan",
    "tendangan_sabit",
    "tendangan_t",
    "kuda_kuda_tengah",
    "kuda_kuda_depan",
    "kuda_kuda_samping",
    "tangkisan_atas",
    "tangkisan_dalam",
    "tangkisan_bawah",
]
