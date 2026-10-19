import json
import math
from pathlib import Path
from sqlalchemy import select, or_
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.entities import ReferenceProfile, EvaluationSession, EvaluationIssue, TrainingSession, now
from app.intelligence.contracts import FEATURE_VERSION


class EvaluationRepository:
    def __init__(self, db: Session):
        self.db = db

    def profiles(self, movement: str):
        rows = self.db.scalars(
            select(ReferenceProfile).where(
                ReferenceProfile.movement == movement, ReferenceProfile.active.is_(True)
            )
        ).all()
        profiles = []
        root = Path(settings.reference_root).resolve()
        for row in rows:
            path = (root / row.artifact_path).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, ValueError):
                continue
            if not isinstance(data, dict):
                continue
            provenance = data.get("provenance", {})
            if (data.get("feature_version") != FEATURE_VERSION
                    or not isinstance(provenance, dict) or provenance.get("debug_partial")):
                continue
            if (
                data.get("movement") != movement
                or data.get("variant") != row.variant
                or data.get("version") != row.version
            ):
                continue
            statistics = data.get("feature_statistics")
            if not isinstance(statistics, dict):
                continue
            if any(not isinstance(stat, dict) or any(
                type(stat.get(key)) not in (int, float) or not math.isfinite(stat[key])
                for key in ("median", "iqr")
            ) for stat in statistics.values()):
                continue
            if sum(stat["iqr"] > 1e-6 for stat in statistics.values()) < 8:
                continue
            profiles.append({**data, "id": row.id})
        return profiles

    def build(self, user_id: int, result: dict, training_session_id: int):
        row = EvaluationSession(
            training_session_id=training_session_id,
            user_id=user_id,
            movement=result["movement"],
            matched_variant=result["matched_variant"],
            reference_profile_id=result["reference_profile_id"],
            score=result["score"],
            status=result["status"],
            analyzer_version=result["model"]["analyzer_version"],
            reference_version=result["model"]["reference_version"],
            result_json=result,
        )
        row.issues = [EvaluationIssue(**issue) for issue in result["issues"]]
        self.db.add(row)
        return row

    def save(self, user_id: int, result: dict):
        # Legacy synchronous endpoint keeps its DTO, but links every new result.
        timestamp = now()
        session = TrainingSession(user_id=user_id, movement=result["movement"],
                                  processing_status="completed", created_at=timestamp, completed_at=timestamp)
        self.db.add(session)
        self.db.flush()
        row = self.build(user_id, result, session.id)
        self.db.commit()
        self.db.refresh(row)
        return row

    def history(self, user_id: int, offset: int, limit: int):
        return self.db.scalars(
            select(EvaluationSession)
            .outerjoin(TrainingSession, TrainingSession.id == EvaluationSession.training_session_id)
            .where(EvaluationSession.user_id == user_id,
                   or_(EvaluationSession.training_session_id.is_(None), TrainingSession.deleted_at.is_(None)))
            .order_by(EvaluationSession.created_at.desc(), EvaluationSession.id.desc())
            .offset(offset)
            .limit(limit)
        ).all()


def is_deleted(db, row):
    if row.training_session_id is None:
        return False
    session = db.get(TrainingSession, row.training_session_id)
    return session is not None and session.deleted_at is not None


def serialize(row: EvaluationSession):
    return {
        **row.result_json,
        "id": row.id,
        "created_at": row.created_at.isoformat() + "Z",
        "coach_notes": [
            {
                "id": n.id,
                "coach_name": n.coach.name,
                "note": n.note,
                "created_at": n.created_at.isoformat() + "Z",
            }
            for n in row.notes
        ],
    }
