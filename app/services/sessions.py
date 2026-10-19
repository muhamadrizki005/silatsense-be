from datetime import timedelta
import hashlib
import json
from pathlib import Path
import time
from uuid import uuid4

from sqlalchemy import func, select, update

from app.core.config import settings
from app.core.errors import DomainError
from app.intelligence.contracts import ANALYZER_VERSION, FEATURE_VERSION
from app.models.entities import AnalysisJob, EvaluationSession, IdempotencyRecord, MediaAsset, TrainingSession, UploadReservation, now
from app.repositories.evaluations import EvaluationRepository
from app.repositories.profiles import lock_user
from app.schemas.sessions import AcceptedSession, MediaOut, SessionFailure, SessionOut
from app.services.probe import probe_video
from app.services.storage import LocalStorage
from app.services.training import required_movement
from app.services.uploads import ALLOWED

FAILURES = {
    "media_expired": "Masa simpan video telah berakhir.",
    "media_unavailable": "Video tidak tersedia.",
    "media_deleted": "Video sudah dihapus.",
    "model_unavailable": "Model pose belum tersedia.",
    "model_version_unavailable": "Versi model pekerjaan tidak tersedia.",
    "analyzer_version_unavailable": "Versi analyzer pekerjaan tidak tersedia.",
    "analysis_timeout": "Analisis melampaui batas waktu.",
    "retry_exhausted": "Analisis gagal setelah batas percobaan.",
    "invalid_video": "Video tidak dapat dianalisis.",
    "analysis_failed": "Analisis gagal.",
}


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def identifier(value):
    if (not value or not value.isascii() or not value.isdigit() or len(value) > 19
            or not 1 <= int(value) <= 2**63 - 1):
        raise DomainError(404, "not_found", "Sesi tidak ditemukan.")
    return int(value)


def get_session(db, owner_id, value):
    session = db.scalar(select(TrainingSession).where(
        TrainingSession.id == identifier(value), TrainingSession.user_id == owner_id,
        TrainingSession.deleted_at.is_(None),
    ))
    if session is None:
        raise DomainError(404, "not_found", "Sesi tidak ditemukan.")
    return session


def read_session(db, owner_id, value):
    session = get_session(db, owner_id, value)
    evaluation = db.scalar(select(EvaluationSession).where(EvaluationSession.training_session_id == session.id))
    asset = db.scalar(select(MediaAsset).where(MediaAsset.session_id == session.id))
    from app.repositories.reviews import bundle
    reviews, assigned = bundle(db, [session])
    return session_out(session, evaluation, asset, reviews.get(session.id), session.user_id in assigned)


def session_out(session, evaluation, asset, review=None, coach_available=False):
    status = "unavailable"
    if asset:
        if asset.deleted_at or asset.deletion_requested_at:
            status = "expired" if asset.expires_at <= now() else "deleted"
        elif asset.expires_at <= now():
            status = "expired"
        elif LocalStorage().exists(asset.storage_key):
            status = "available"
    media = MediaOut(
        status=status, expiresAt=asset.expires_at if asset else None,
        mimeType=asset.mime_type if asset else None, byteSize=asset.byte_size if asset else None,
        durationSeconds=asset.duration_seconds if asset else None,
        width=asset.width if asset else None, height=asset.height if asset else None,
        playbackPath=f"/api/v1/member/sessions/{session.id}/video" if status == "available" else None,
    )
    return SessionOut(
        id=str(session.id), movementSlug="kuda-kuda" if session.movement == "kuda_kuda" else session.movement,
        createdAt=session.created_at, uploadedAt=session.uploaded_at, startedAt=session.started_at,
        completedAt=session.completed_at, processingStatus=session.processing_status,
        analysisStatus=evaluation.status if evaluation else None,
        evaluationId=str(evaluation.id) if evaluation else None,
        reviewStatus=review.decision if review else "pending",
        reviewAvailable=coach_available and session.processing_status == "completed",
        retryOf=str(session.retry_of) if session.retry_of else None,
        acknowledgedAt=session.acknowledged_at, media=media,
        error=SessionFailure(code=session.error_code, detail=FAILURES.get(session.error_code, "Analisis gagal."))
        if session.error_code else None,
    )


def _record(db, user_id, key_hash):
    return db.scalar(select(IdempotencyRecord).where(
        IdempotencyRecord.user_id == user_id, IdempotencyRecord.operation == "upload",
        IdempotencyRecord.key_hash == key_hash,
    ))


def _authorized_lock(db, user_id, auth_version):
    # Discard the dependency's repeatable-read snapshot before quota reads.
    db.rollback()
    user = lock_user(db, user_id)
    if not user or user.auth_version != auth_version:
        raise DomainError(401, "unauthenticated", "Silakan masuk kembali.")
    return user


def _replay(db, record, fingerprint):
    if record.fingerprint != fingerprint:
        raise DomainError(409, "idempotency_conflict", "Key sudah dipakai untuk unggahan yang berbeda.")
    session = db.get(TrainingSession, record.session_id)
    if not session or session.deleted_at:
        raise DomainError(409, "idempotency_conflict", "Sesi sebelumnya sudah dihapus.")
    return AcceptedSession.model_validate(record.response_json)


def _release(db, owner_id, reservation_id, final_key, storage):
    # In an ambiguous COMMIT failure, check authoritative DB state before unlink.
    try:
        db.rollback()
        lock_user(db, owner_id)
        linked = db.scalar(select(MediaAsset.id).where(MediaAsset.storage_key == final_key))
        if linked is None:
            storage.delete(storage.staging_key(final_key))
            storage.delete(final_key)
        row = db.get(UploadReservation, reservation_id)
        if row:
            db.delete(row)
        db.commit()
    except Exception:
        db.rollback()  # Cleanup CLI reconciles files/reservations after a DB/IO outage.


def accept_upload(db, user, movement_slug, video, idempotency_key, retry_of=None):
    storage = LocalStorage()
    owner_id, auth_version = user.id, user.auth_version
    reservation_id = final_key = None
    try:
        if not idempotency_key.strip():
            raise DomainError(422, "validation_error", "Idempotency-Key tidak boleh kosong.")
        suffix = Path(video.filename or "").suffix.lower()
        if suffix not in ALLOWED or video.content_type not in ALLOWED[suffix]:
            raise DomainError(415, "unsupported_media_type", "Gunakan MP4, MOV, atau WebM.")
        key_hash = hashlib.sha256(idempotency_key.encode()).hexdigest()
        _authorized_lock(db, owner_id, auth_version)
        movement = required_movement(db, movement_slug).slug
        retry_id = None
        if retry_of is not None:
            previous = get_session(db, owner_id, retry_of)
            if previous.movement != movement:
                raise DomainError(422, "validation_error", "Kategori retryOf harus sama.")
            retry_id = previous.id
        existing = _record(db, owner_id, key_hash)
        max_bytes = settings.max_video_mb * 1024 * 1024
        if not existing:
            reserved = video.size if isinstance(video.size, int) else max_bytes
            if reserved > max_bytes:
                raise DomainError(413, "upload_too_large", "Video melebihi batas ukuran.")
            busy = db.scalar(select(func.count()).select_from(TrainingSession).where(
                TrainingSession.user_id == owner_id, TrainingSession.deleted_at.is_(None),
                TrainingSession.processing_status.in_(["queued", "processing"]),
            ))
            reservations = db.scalar(select(func.count()).select_from(UploadReservation).where(UploadReservation.user_id == owner_id))
            used = db.scalar(select(func.coalesce(func.sum(MediaAsset.byte_size), 0)).where(
                MediaAsset.user_id == owner_id, MediaAsset.deleted_at.is_(None),
            ))
            held = db.scalar(select(func.coalesce(func.sum(UploadReservation.reserved_bytes), 0)).where(UploadReservation.user_id == owner_id))
            if busy + reservations >= settings.max_pending_sessions or used + held + reserved > settings.upload_quota_mb * 1024 * 1024:
                raise DomainError(429, "quota_exceeded", "Kuota video atau antrean latihan penuh.")
            reservation_id = uuid4().hex
            final_key = f"objects/{reservation_id}{suffix}"
            db.add(UploadReservation(id=reservation_id, user_id=owner_id, storage_key=final_key,
                                     reserved_bytes=reserved,
                                     expires_at=now() + timedelta(seconds=settings.upload_reservation_seconds)))
        db.commit()
        size, digest = 0, hashlib.sha256()
        target = storage.create(storage.staging_key(final_key)) if final_key else None
        heartbeat_at = time.monotonic()
        try:
            while chunk := video.file.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise DomainError(413, "upload_too_large", "Video melebihi batas ukuran.")
                digest.update(chunk)
                if target:
                    target.write(chunk)
                if reservation_id and time.monotonic() - heartbeat_at > 15:
                    updated = db.execute(update(UploadReservation).where(
                        UploadReservation.id == reservation_id, UploadReservation.expires_at > now(),
                    ).values(expires_at=now() + timedelta(seconds=settings.upload_reservation_seconds)))
                    db.commit()
                    if updated.rowcount != 1:
                        raise DomainError(503, "upload_expired", "Reservasi upload berakhir.")
                    heartbeat_at = time.monotonic()
        finally:
            if target:
                target.close()
        uploaded_at = now()
        if not size:
            raise DomainError(422, "invalid_video", "Video kosong.")
        fingerprint = canonical_hash({"checksum": digest.hexdigest(), "movementSlug": movement_slug, "retryOf": retry_id})
        _authorized_lock(db, owner_id, auth_version)
        record = _record(db, owner_id, key_hash)
        if record:
            result = _replay(db, record, fingerprint)
            db.commit()
            return result
        db.commit()
        metadata = probe_video(storage.path(storage.staging_key(final_key)), suffix)
        profiles = EvaluationRepository(db).profiles(movement)
        snapshot = [{"profile": profile, "checksum": canonical_hash(profile)} for profile in profiles]
        model_path = Path(settings.pose_model_path).resolve()
        model_checksum = hashlib.sha256(model_path.read_bytes()).hexdigest() if model_path.is_file() else None
        _authorized_lock(db, owner_id, auth_version)
        record = _record(db, owner_id, key_hash)
        if record:
            result = _replay(db, record, fingerprint)
            db.commit()
            return result
        reservation = db.get(UploadReservation, reservation_id)
        if not reservation or reservation.expires_at <= now() or size > reservation.reserved_bytes:
            raise DomainError(503, "upload_expired", "Reservasi upload tidak valid.")
        required_movement(db, movement_slug)
        if retry_id:
            get_session(db, owner_id, str(retry_id))
        session = TrainingSession(user_id=owner_id, movement=movement, processing_status="queued",
                                  uploaded_at=uploaded_at, retry_of=retry_id)
        db.add(session)
        db.flush()
        storage.finalize(storage.staging_key(final_key), final_key)
        db.add(MediaAsset(session_id=session.id, user_id=owner_id, storage_key=final_key,
                          mime_type=metadata["mimeType"], byte_size=size, checksum=digest.hexdigest(),
                          duration_seconds=metadata["durationSeconds"], width=metadata["width"], height=metadata["height"],
                          expires_at=uploaded_at + timedelta(hours=24)))
        db.add(AnalysisJob(session_id=session.id, state="queued", reference_snapshot=snapshot,
                           processing_config={"analyzerVersion": ANALYZER_VERSION, "featureVersion": FEATURE_VERSION,
                                              "modelPath": str(model_path), "modelChecksum": model_checksum,
                                              "sampleFps": settings.sample_fps, "maxSeconds": settings.max_video_seconds}))
        result = AcceptedSession(sessionId=str(session.id), uploadedAt=uploaded_at,
                                 statusUrl=f"/api/v1/member/sessions/{session.id}",
                                 evaluationUrl=f"/api/v1/member/sessions/{session.id}/evaluation")
        db.add(IdempotencyRecord(user_id=owner_id, operation="upload", key_hash=key_hash,
                                 fingerprint=fingerprint, session_id=session.id,
                                 response_json=result.model_dump(mode="json")))
        db.delete(reservation)
        db.commit()
        return result
    finally:
        video.file.close()
        if reservation_id:
            _release(db, owner_id, reservation_id, final_key, storage)
