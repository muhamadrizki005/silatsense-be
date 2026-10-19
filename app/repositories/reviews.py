from sqlalchemy import select
from app.models.entities import CoachAssignment, FollowUpTask, ReviewHead, ReviewRevision
from app.schemas.reviews import PublishedReview, TaskOut


def bundle(db, sessions):
    ids = [row.id for row in sessions]
    if not ids:
        return {}, set()
    reviews = {row.session_id: PublishedReview.model_validate(row.payload) for row in db.scalars(
        select(ReviewRevision).join(ReviewHead, ReviewHead.review_id == ReviewRevision.id)
        .where(ReviewHead.session_id.in_(ids))).all()}
    assigned = set(db.scalars(select(CoachAssignment.member_id).where(
        CoachAssignment.member_id.in_({row.user_id for row in sessions}))).all())
    return reviews, assigned


def history(db, session_id):
    return [PublishedReview.model_validate(row.payload) for row in db.scalars(select(ReviewRevision)
        .where(ReviewRevision.session_id == session_id).order_by(ReviewRevision.revision)).all()]


def task_out(row, review):
    return TaskOut(id=str(row.id), sessionId=str(row.session_id), reviewId=str(row.review_id),
        author=review.payload["author"], instruction=row.instruction, status=row.status,
        createdAt=row.created_at, updatedAt=row.updated_at)


def tasks(db, session_id):
    return [task_out(row, review) for row, review in db.execute(select(FollowUpTask, ReviewRevision)
        .join(ReviewRevision, ReviewRevision.id == FollowUpTask.review_id)
        .where(FollowUpTask.session_id == session_id).order_by(FollowUpTask.created_at, FollowUpTask.id))]
