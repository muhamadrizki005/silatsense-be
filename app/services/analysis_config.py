"""Freeze analysis selection at upload time, without loading native CV libraries."""

import hashlib
from pathlib import Path

from app.core.config import settings
from app.core.errors import DomainError
from app.intelligence.contracts import ANALYZER_VERSION, FEATURE_VERSION
from app.intelligence.coach_contracts import (
    ANALYZER_VERSION as COACH_VERSION,
    FEATURE_VERSION as COACH_FEATURES,
)
from app.intelligence.movement_catalog import MOVEMENTS


def validate_target(category, movement_id):
    category = "kuda_kuda" if category == "kuda-kuda" else category
    if movement_id is not None and (
        movement_id not in MOVEMENTS or MOVEMENTS[movement_id][0] != category
    ):
        raise DomainError(
            422, "invalid_movement_id", "movementId tidak sesuai kategori latihan."
        )
    if settings.analysis_mode == "coach-reference":
        if movement_id is None:
            raise DomainError(
                422,
                "movement_id_required",
                "Pilih movementId gerakan yang akan dilatih.",
            )
        if not settings.coach_reference_sha256:
            raise DomainError(
                503,
                "reference_configuration_required",
                "Checksum referensi Coach belum dikonfigurasi.",
            )


def processing_config(category, movement_id=None, *, remote=False):
    validate_target(category, movement_id)
    path = Path(settings.pose_model_path).resolve()
    checksum = (
        settings.pose_model_sha256
        if remote
        else (hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None)
    )
    config = {
        "analyzerVersion": ANALYZER_VERSION,
        "featureVersion": FEATURE_VERSION,
        "modelPath": settings.pose_model_path if remote else str(path),
        "modelChecksum": checksum,
        "sampleFps": settings.sample_fps,
        "maxSeconds": settings.max_video_seconds,
    }
    if remote:
        config["remoteUpload"] = True
    if settings.analysis_mode == "coach-reference":
        config.update(
            analyzerVersion=COACH_VERSION,
            featureVersion=COACH_FEATURES,
            method="coach-reference-dtw",
            movementId=movement_id,
            referenceModelChecksum=settings.coach_reference_sha256,
        )
    return config
