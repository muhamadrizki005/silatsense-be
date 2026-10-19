from datetime import timedelta, timezone
import logging

from sqlalchemy import select, or_

from app.core.config import settings
from app.models.entities import AnalysisJob, MediaAsset, TrainingSession, UploadReservation, now
from app.repositories.jobs import _terminal
from app.repositories.profiles import lock_user
from app.services.storage import LocalStorage

logger = logging.getLogger(__name__)


def cleanup_once(factory):
    storage = LocalStorage()
    deleted = 0
    timestamp = now()
    with factory() as db:
        reservation_ids = db.scalars(select(UploadReservation.id).where(
            UploadReservation.expires_at <= timestamp,
        ).limit(settings.cleanup_batch_size)).all()
    for reservation_id in reservation_ids:
        with factory() as db:
            hint = db.get(UploadReservation, reservation_id)
            if hint is None:
                continue
            owner_id = hint.user_id
            db.rollback()
            lock_user(db, owner_id)
            reservation = db.get(UploadReservation, reservation_id)
            if not reservation or reservation.expires_at > now():
                continue
            linked = db.scalar(select(MediaAsset.id).where(MediaAsset.storage_key == reservation.storage_key))
            try:
                if linked is None:
                    storage.delete(storage.staging_key(reservation.storage_key))
                    storage.delete(reservation.storage_key)
                db.delete(reservation)
                db.commit()
            except OSError:
                db.rollback()  # Locked Windows upload handle: retry on the next cycle.
    with factory() as db:
        media_ids = db.scalars(select(MediaAsset.id).where(
            MediaAsset.deleted_at.is_(None), or_(MediaAsset.expires_at <= timestamp, MediaAsset.deletion_requested_at.is_not(None)),
        ).limit(settings.cleanup_batch_size)).all()
    for media_id in media_ids:
        with factory() as db:
            hint = db.get(MediaAsset, media_id)
            if hint is None:
                continue
            session_id = hint.session_id
            db.rollback()
            # Same order as claim/finish: job -> session -> media.
            job = db.scalar(select(AnalysisJob).where(AnalysisJob.session_id == session_id).with_for_update())
            session = db.scalar(select(TrainingSession).where(TrainingSession.id == session_id).with_for_update())
            media = db.scalar(select(MediaAsset).where(MediaAsset.id == media_id).with_for_update())
            timestamp = now()
            if not media or media.deleted_at or (media.expires_at > timestamp and not media.deletion_requested_at):
                continue
            media.deletion_requested_at = media.deletion_requested_at or timestamp
            active_reader = job and job.lease_until and job.lease_until > timestamp
            if job and job.state in {"queued", "processing"}:
                _terminal(job, session, "media_expired" if media.expires_at <= timestamp else "media_deleted", timestamp)
            if active_reader:
                db.commit()  # Fence first; do not unlink while the lease still protects a reader.
                continue
            try:
                storage.delete(media.storage_key)
                media.deleted_at = timestamp
                db.commit()
                deleted += 1
            except OSError:
                db.rollback()
    # Orphan reconciliation never follows symlinks or deletes arbitrary filenames.
    with factory() as db:
        protected = set(db.scalars(select(MediaAsset.storage_key)).all())
        for key in db.scalars(select(UploadReservation.storage_key)).all():
            protected.update((key, storage.staging_key(key)))
    cutoff = (now().replace(tzinfo=timezone.utc) - timedelta(seconds=settings.orphan_grace_seconds)).timestamp()
    for key, modified_at in storage.candidates():
        if key not in protected and modified_at < cutoff:
            try:
                # Recheck in a fresh transaction: a paused scan must not delete
                # a file whose upload committed since the protected-set snapshot.
                with factory() as db:
                    linked = db.scalar(select(MediaAsset.id).where(MediaAsset.storage_key == key))
                    reserved = db.scalar(select(UploadReservation.id).where(
                        UploadReservation.id == key.split("/")[1].split(".")[0]))
                    if linked is not None or reserved is not None:
                        continue
                storage.delete(key)
                deleted += 1
            except OSError:
                pass
    logger.info("cleanup_completed deletedCount=%s", deleted)
    return deleted
