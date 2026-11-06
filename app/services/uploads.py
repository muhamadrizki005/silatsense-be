"""Small JSON control requests; video bytes travel directly to private B2."""

from datetime import timedelta, timezone
import hashlib
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select

from app.core.config import settings
from app.core.errors import DomainError
from app.intelligence.contracts import ANALYZER_VERSION, FEATURE_VERSION
from app.models.entities import (
    AnalysisJob,
    DirectUpload,
    MediaAsset,
    TrainingSession,
    UploadReservation,
    now,
)
from app.repositories.evaluations import EvaluationRepository
from app.schemas.sessions import AcceptedSession
from app.schemas.uploads import UploadTicket
from app.services.sessions import _authorized_lock, canonical_hash, get_session
from app.services.storage import StorageUnavailable, get_storage
from app.services.training import required_movement
from app.services.video import ALLOWED


def storage_for_upload():
    if settings.storage_adapter != "b2":
        raise DomainError(
            503, "direct_upload_unavailable", "Direct upload memerlukan storage B2."
        )
    if not settings.pose_model_sha256:
        raise DomainError(
            503,
            "worker_configuration_required",
            "Checksum model worker belum dikonfigurasi.",
        )
    try:
        return get_storage()
    except OSError:
        raise DomainError(
            503, "storage_unavailable", "Storage tidak tersedia."
        ) from None


def _owned(db, user_id, upload_id):
    row = db.get(DirectUpload, upload_id)
    if row is None or row.user_id != user_id:
        raise DomainError(404, "not_found", "Upload tidak ditemukan.")
    return row


def _accepted(db, row):
    session = db.get(TrainingSession, row.session_id)
    if not session or session.deleted_at:
        raise DomainError(409, "upload_deleted", "Sesi upload sudah dihapus.")
    return AcceptedSession.model_validate(row.response_json)


def _ticket(db, row, storage):
    accepted = _accepted(db, row) if row.session_id else None
    remaining = int((row.expires_at - now()).total_seconds())
    if not accepted and remaining <= 0:
        raise DomainError(
            410, "upload_expired", "Reservasi upload telah berakhir. Gunakan key baru."
        )
    request = row.request_json
    suffix = Path(request["filename"]).suffix.lower()
    staging = storage.staging_key(f"objects/{row.id}{suffix}")
    return UploadTicket(
        uploadId=row.id,
        uploadUrl=None
        if accepted
        else storage.presign(
            staging, request["byteSize"], request["mimeType"], remaining
        ),
        headers={} if accepted else {"Content-Type": request["mimeType"]},
        expiresAt=row.expires_at,
        completePath=f"/api/v1/member/uploads/{row.id}/complete",
        acceptedSession=accepted,
    )


def initiate_upload(db, user, request, key):
    storage = storage_for_upload()
    if not key.strip():
        raise DomainError(
            422, "validation_error", "Idempotency-Key tidak boleh kosong."
        )
    payload = request.model_dump()
    suffix = Path(request.filename).suffix.lower()
    if suffix not in ALLOWED or request.mimeType not in ALLOWED[suffix]:
        raise DomainError(
            415, "unsupported_media_type", "Gunakan MP4, MOV, atau WebM yang sesuai."
        )
    if request.byteSize > settings.max_video_mb * 1024 * 1024:
        raise DomainError(413, "upload_too_large", "Video melebihi batas ukuran.")
    owner, version = user.id, user.auth_version
    _authorized_lock(db, owner, version)
    key_hash, fingerprint = (
        hashlib.sha256(key.encode()).hexdigest(),
        canonical_hash(payload),
    )
    row = db.scalar(
        select(DirectUpload).where(
            DirectUpload.user_id == owner, DirectUpload.key_hash == key_hash
        )
    )
    try:
        if row:
            if row.fingerprint != fingerprint:
                raise DomainError(
                    409,
                    "idempotency_conflict",
                    "Key sudah dipakai untuk unggahan berbeda.",
                )
            result = _ticket(db, row, storage)
            db.commit()
            return result
        required_movement(db, request.movementSlug)
        if request.retryOf:
            previous = get_session(db, owner, request.retryOf)
            movement = (
                "kuda_kuda"
                if request.movementSlug == "kuda-kuda"
                else request.movementSlug
            )
            if previous.movement != movement:
                raise DomainError(
                    422, "validation_error", "Kategori retryOf harus sama."
                )
        busy = db.scalar(
            select(func.count())
            .select_from(TrainingSession)
            .where(
                TrainingSession.user_id == owner,
                TrainingSession.deleted_at.is_(None),
                TrainingSession.processing_status.in_(["queued", "processing"]),
            )
        )
        reservations = db.scalar(
            select(func.count())
            .select_from(UploadReservation)
            .where(UploadReservation.user_id == owner)
        )
        held = db.scalar(
            select(func.coalesce(func.sum(UploadReservation.reserved_bytes), 0)).where(
                UploadReservation.user_id == owner
            )
        )
        used = db.scalar(
            select(func.coalesce(func.sum(MediaAsset.byte_size), 0)).where(
                MediaAsset.user_id == owner, MediaAsset.deleted_at.is_(None)
            )
        )
        if (
            busy + reservations >= settings.max_pending_sessions
            or used + held + request.byteSize > settings.upload_quota_mb * 1024 * 1024
        ):
            raise DomainError(
                429, "quota_exceeded", "Kuota video atau antrean latihan penuh."
            )
        upload_id = uuid4().hex
        expiry = now() + timedelta(seconds=settings.upload_reservation_seconds)
        row = DirectUpload(
            id=upload_id,
            user_id=owner,
            key_hash=key_hash,
            fingerprint=fingerprint,
            request_json=payload,
            expires_at=expiry,
        )
        db.add(row)
        db.add(
            UploadReservation(
                id=upload_id,
                user_id=owner,
                storage_key=f"objects/{upload_id}{suffix}",
                reserved_bytes=request.byteSize,
                expires_at=expiry,
            )
        )
        result = _ticket(db, row, storage)
        db.commit()
        return result
    except StorageUnavailable:
        db.rollback()
        raise DomainError(
            503, "storage_unavailable", "Storage tidak tersedia."
        ) from None


def complete_upload(db, user, upload_id):
    storage = storage_for_upload()
    owner, version = user.id, user.auth_version
    _authorized_lock(db, owner, version)
    row = _owned(db, owner, upload_id)
    if row.session_id:
        result = _accepted(db, row)
        db.commit()
        return result
    reservation = db.get(UploadReservation, upload_id)
    if not reservation or row.expires_at <= now():
        raise DomainError(410, "upload_expired", "Reservasi upload telah berakhir.")
    request = row.request_json
    final_key = reservation.storage_key
    staging = storage.staging_key(final_key)
    try:
        head = storage.head(staging)
        if (
            head["ContentLength"] != request["byteSize"]
            or head.get("ContentType") != request["mimeType"]
        ):
            raise DomainError(
                422, "upload_mismatch", "Ukuran atau tipe file tidak sesuai reservasi."
            )
        uploaded_at = head["LastModified"].astimezone(timezone.utc).replace(tzinfo=None)
        if uploaded_at > row.expires_at or uploaded_at + timedelta(hours=24) <= now():
            raise DomainError(410, "upload_expired", "Upload telah kedaluwarsa.")
        movement = required_movement(db, request["movementSlug"]).slug
        retry_id = (
            get_session(db, owner, request["retryOf"]).id
            if request["retryOf"]
            else None
        )
        profiles = EvaluationRepository(db).profiles(movement)
        snapshot = [
            {"profile": profile, "checksum": canonical_hash(profile)}
            for profile in profiles
        ]
        # API never decodes video or requires the .task artifact in Vercel.
        storage.finalize_version(staging, final_key, head.get("VersionId"))
        if now() >= row.expires_at:
            raise DomainError(410, "upload_expired", "Reservasi upload telah berakhir.")
        session = TrainingSession(
            user_id=owner,
            movement=movement,
            processing_status="queued",
            uploaded_at=uploaded_at,
            retry_of=retry_id,
        )
        db.add(session)
        db.flush()
        db.add(
            MediaAsset(
                session_id=session.id,
                user_id=owner,
                storage_key=final_key,
                mime_type=request["mimeType"],
                byte_size=request["byteSize"],
                checksum=request["sha256"],
                duration_seconds=None,
                width=None,
                height=None,
                expires_at=uploaded_at + timedelta(hours=24),
            )
        )
        db.add(
            AnalysisJob(
                session_id=session.id,
                state="queued",
                reference_snapshot=snapshot,
                processing_config={
                    "analyzerVersion": ANALYZER_VERSION,
                    "featureVersion": FEATURE_VERSION,
                    "modelPath": settings.pose_model_path,
                    "modelChecksum": settings.pose_model_sha256,
                    "sampleFps": settings.sample_fps,
                    "maxSeconds": settings.max_video_seconds,
                    "remoteUpload": True,
                },
            )
        )
        result = AcceptedSession(
            sessionId=str(session.id),
            uploadedAt=uploaded_at,
            statusUrl=f"/api/v1/member/sessions/{session.id}",
            evaluationUrl=f"/api/v1/member/sessions/{session.id}/evaluation",
        )
        row.session_id, row.response_json = session.id, result.model_dump(mode="json")
        db.delete(reservation)
        db.commit()
        return result
    except FileNotFoundError:
        db.rollback()
        raise DomainError(
            409,
            "upload_incomplete",
            "File belum tersedia. Selesaikan PUT terlebih dahulu.",
        ) from None
    except StorageUnavailable:
        db.rollback()
        raise DomainError(
            503, "storage_unavailable", "Storage tidak tersedia. Coba complete kembali."
        ) from None
