"""Historical result fixtures use the live repository, without an HTTP legacy API."""

from app.models.entities import TrainingSession, now
from app.repositories.evaluations import EvaluationRepository


def save_completed_evaluation(db, user_id, result):
    timestamp = now()
    session = TrainingSession(
        user_id=user_id,
        movement=result["movement"],
        processing_status="completed",
        created_at=timestamp,
        completed_at=timestamp,
    )
    db.add(session)
    db.flush()
    row = EvaluationRepository(db).build(user_id, result, session.id)
    db.commit()
    db.refresh(row)
    return row
