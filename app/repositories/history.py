from sqlalchemy import and_, func, or_, select

from app.models.entities import CoachNote, CoachProfile, EvaluationSession, MediaAsset, Movement, TrainingSession, User, ReviewHead, ReviewRevision
from app.repositories.training import PUBLIC_TO_INTERNAL


def visible(owner_id):
    return (TrainingSession.user_id == owner_id, TrainingSession.deleted_at.is_(None))


def history_rows(db, owner_id, query, position=None):
    statement = select(TrainingSession).where(*visible(owner_id))
    if query.movementSlug is not None:
        statement = statement.where(TrainingSession.movement == PUBLIC_TO_INTERNAL[query.movementSlug])
    if query.processingStatus is not None:
        statement = statement.where(TrainingSession.processing_status == query.processingStatus)
    if query.reviewStatus is not None:
        reviewed = select(ReviewHead.session_id).join(ReviewRevision, ReviewRevision.id == ReviewHead.review_id)
        statement = statement.where(TrainingSession.id.not_in(select(ReviewHead.session_id))) if query.reviewStatus == "pending" else (
            statement.where(TrainingSession.id.in_(reviewed.where(ReviewRevision.decision == query.reviewStatus))))
    if query.fromAt is not None:
        statement = statement.where(TrainingSession.created_at >= query.fromAt.replace(tzinfo=None))
    if query.toAt is not None:
        statement = statement.where(TrainingSession.created_at < query.toAt.replace(tzinfo=None))
    if position is not None:
        timestamp, sid = position
        statement = statement.where(or_(TrainingSession.created_at < timestamp,
            and_(TrainingSession.created_at == timestamp, TrainingSession.id < sid)))
    return db.scalars(statement.order_by(TrainingSession.created_at.desc(), TrainingSession.id.desc())
                      .limit(query.limit + 1)).all()


def related(db, rows):
    ids = [row.id for row in rows]
    if not ids:
        return {}, {}, {}
    evaluations = {row.training_session_id: row for row in db.scalars(select(EvaluationSession).where(
        EvaluationSession.training_session_id.in_(ids))).all()}
    media = {row.session_id: row for row in db.scalars(select(MediaAsset).where(MediaAsset.session_id.in_(ids))).all()}
    movements = {row.slug: row.name for row in db.scalars(select(Movement).where(
        Movement.slug.in_({row.movement for row in rows}))).all()}
    return evaluations, media, movements


def notes(db, owner_id, session_id=None, latest=False):
    statement = select(CoachNote, User, CoachProfile).join(
        EvaluationSession, EvaluationSession.id == CoachNote.evaluation_id,
    ).join(TrainingSession, TrainingSession.id == EvaluationSession.training_session_id).join(
        User, User.id == CoachNote.coach_id,
    ).outerjoin(CoachProfile, CoachProfile.user_id == User.id).where(
        *visible(owner_id), EvaluationSession.user_id == owner_id,
    )
    if session_id is not None:
        statement = statement.where(TrainingSession.id == session_id)
    if latest:
        return db.execute(statement.order_by(CoachNote.created_at.desc(), CoachNote.id.desc()).limit(1)).first()
    return db.execute(statement.order_by(CoachNote.created_at, CoachNote.id)).all()


def last_session(db, owner_id):
    return db.scalar(select(TrainingSession).where(*visible(owner_id), TrainingSession.processing_status == "completed")
        .order_by(TrainingSession.completed_at.desc(), TrainingSession.id.desc()).limit(1))


def movement_counts(db, owner_id):
    return db.execute(select(TrainingSession.movement, func.count()).where(
        *visible(owner_id), TrainingSession.processing_status == "completed",
    ).group_by(TrainingSession.movement)).all()


def movement_order(db):
    return db.scalars(select(Movement).where(Movement.slug.in_(PUBLIC_TO_INTERNAL.values()))
        .order_by(Movement.display_order, Movement.id)).all()


def week_rows(db, owner_id, start, end):
    return db.execute(select(TrainingSession.completed_at, MediaAsset.duration_seconds).outerjoin(
        MediaAsset, MediaAsset.session_id == TrainingSession.id,
    ).where(*visible(owner_id), TrainingSession.processing_status == "completed",
        TrainingSession.completed_at >= start, TrainingSession.completed_at < end).execution_options(yield_per=500))
