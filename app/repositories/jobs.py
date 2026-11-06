from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from uuid import uuid4

from sqlalchemy import and_, or_, select

from app.core.config import settings
from app.models.entities import AnalysisJob, MediaAsset, TrainingSession, now
from app.repositories.evaluations import EvaluationRepository
from app.schemas.analysis import AnalysisSummary, AnalysisIssue, AnalysisModel
from app.schemas.results import Measurement, PoseData


@dataclass(frozen=True)
class Claim:
    job_id: int
    session_id: int
    token: str
    storage_key: str
    expires_at: datetime
    movement: str
    references: list
    config: dict
    checksum: str | None = None


def _terminal(job, session, code, timestamp):
    job.state, job.last_error_code, job.finished_at = "failed", code, timestamp
    job.claim_token = None
    session.processing_status, session.error_code, session.completed_at = "failed", code, timestamp


def claim_statement(timestamp, dialect):
    # MySQL 5.7 cannot parse SKIP LOCKED. Plain FOR UPDATE still makes
    # claims atomic; concurrent workers wait rather than skip a locked job.
    name = dialect.name
    version = dialect.server_version_info or ()
    if name in {"mysql", "mariadb"}:
        mariadb = name == "mariadb" or getattr(dialect, "is_mariadb", False)
        skip_locked = version >= ((10, 6) if mariadb else (8, 0, 1))
    else:
        skip_locked = name == "postgresql"
    return select(AnalysisJob).where(or_(
        and_(AnalysisJob.state == "queued", AnalysisJob.available_at <= timestamp),
        and_(AnalysisJob.state == "processing", AnalysisJob.lease_until <= timestamp),
    )).order_by(AnalysisJob.available_at, AnalysisJob.id).limit(1).with_for_update(skip_locked=skip_locked)


class JobRepository:
    def __init__(self, factory):
        self.factory = factory

    def claim(self, worker_id):
        timestamp = now()
        with self.factory() as db:
            # Initialize the dialect through the real connection before
            # checking server_version_info (it is None before first connect).
            job = db.scalar(claim_statement(timestamp, db.connection().dialect))
            if job is None:
                return None
            session = db.scalar(select(TrainingSession).where(TrainingSession.id == job.session_id).with_for_update())
            media = db.scalar(select(MediaAsset).where(MediaAsset.session_id == session.id).with_for_update())
            # A legacy server may have waited for row locks. Start the lease
            # and check media expiry after those locks have been acquired.
            timestamp = now()
            if session.deleted_at or not media or media.deleted_at or media.deletion_requested_at or media.expires_at <= timestamp:
                _terminal(job, session, "media_expired" if media and media.expires_at <= timestamp else "media_unavailable", timestamp)
                db.commit()
                return None
            if job.attempt >= settings.worker_max_attempts:
                _terminal(job, session, "retry_exhausted", timestamp)
                db.commit()
                return None
            job.state, job.attempt = "processing", job.attempt + 1
            job.claim_token, job.worker_id = uuid4().hex, worker_id
            job.lease_until = timestamp + timedelta(seconds=settings.worker_lease_seconds)
            job.last_error_code = None
            session.processing_status, session.error_code = "processing", None
            session.started_at = session.started_at or timestamp
            claimed = Claim(job.id, session.id, job.claim_token, media.storage_key, media.expires_at,
                            session.movement, job.reference_snapshot, job.processing_config, media.checksum)
            db.commit()
            return claimed

    def _owned(self, db, claim):
        job = db.scalar(select(AnalysisJob).where(AnalysisJob.id == claim.job_id).with_for_update())
        timestamp = now()
        if (not job or job.state != "processing" or job.claim_token != claim.token
                or not job.lease_until or job.lease_until <= timestamp):
            return None, None
        session = db.scalar(select(TrainingSession).where(TrainingSession.id == job.session_id).with_for_update())
        return job, session

    def heartbeat(self, claim):
        with self.factory() as db:
            job, session = self._owned(db, claim)
            if not job:
                return False
            if session.deleted_at or claim.expires_at <= now():
                _terminal(job, session, "media_expired" if claim.expires_at <= now() else "media_unavailable", now())
                db.commit()
                return False
            job.lease_until = now() + timedelta(seconds=settings.worker_lease_seconds)
            db.commit()
            return True

    def complete(self, claim, result):
        # Only trusted analyzer output is accepted; reject malformed/NaN results.
        json.dumps(result, allow_nan=False)
        AnalysisSummary.model_validate(result["analysis"])
        AnalysisModel.model_validate(result["model"])
        if result.get("pose") is not None:
            PoseData.model_validate(result["pose"])
        for measurement in result.get("measurements", []):
            Measurement.model_validate(measurement)
        for issue in result["issues"]:
            AnalysisIssue.model_validate(issue)
        if result["movement"] != claim.movement or result["status"] not in {
            "experimental", "reference_not_ready", "insufficient_pose", "insufficient_features",
        }:
            raise ValueError("Invalid analysis result")
        score = result["score"]
        if (result["status"] == "experimental") != (score is not None):
            raise ValueError("Score must match analysis status")
        if score is not None and (type(score) not in (int, float) or not 0 <= score <= 100):
            raise ValueError("Invalid experimental score")
        with self.factory() as db:
            job, session = self._owned(db, claim)
            if not job:
                return False
            if session.deleted_at or claim.expires_at <= now():
                _terminal(job, session, "media_expired" if claim.expires_at <= now() else "media_unavailable", now())
                db.commit()
                return False
            result["model"]["feature_version"] = claim.config["featureVersion"]
            EvaluationRepository(db).build(session.user_id, result, session.id)
            timestamp = now()
            session.processing_status, session.error_code, session.completed_at = "completed", None, timestamp
            job.state, job.finished_at, job.claim_token, job.lease_until = "completed", timestamp, None, None
            db.commit()
            return True

    def validated_media(self, claim, metadata):
        with self.factory() as db:
            job, session = self._owned(db, claim)
            if not job or session.deleted_at or claim.expires_at <= now():
                return False
            media = db.scalar(select(MediaAsset).where(MediaAsset.session_id == claim.session_id).with_for_update())
            if not media or media.deleted_at or media.deletion_requested_at:
                return False
            media.duration_seconds = metadata["durationSeconds"]
            media.width, media.height, media.mime_type = metadata["width"], metadata["height"], metadata["mimeType"]
            db.commit()
            return True

    def fail(self, claim, code, transient=False):
        with self.factory() as db:
            job, session = self._owned(db, claim)
            if not job:
                return False
            timestamp = now()
            if claim.expires_at <= timestamp:
                code, transient = "media_expired", False
            delay = 5 if job.attempt == 1 else 30
            if (transient and not session.deleted_at and job.attempt < settings.worker_max_attempts
                    and timestamp + timedelta(seconds=delay) < claim.expires_at):
                job.state, job.available_at = "queued", timestamp + timedelta(seconds=delay)
                job.last_error_code, job.claim_token, job.lease_until = code, None, None
                session.processing_status, session.error_code = "queued", None
            else:
                _terminal(job, session, code if not transient else "retry_exhausted", timestamp)
                job.lease_until = None
            db.commit()
            return True
