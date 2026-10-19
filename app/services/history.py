from datetime import datetime, timedelta, timezone
from math import isfinite

from app.core.cursors import decode_cursor, encode_cursor
from app.models.entities import now
from app.repositories import history as repository
from app.repositories.profiles import activity_summary
from app.repositories.training import MOVEMENTS
from app.schemas.domain import CoachIdentity
from app.schemas.history import DailyActivity, Dashboard, HistoryItem, HistoryPage, PublishedNote, SessionDetail
from app.services.results import evaluation_out
from app.services.sessions import get_session, session_out
from app.repositories import reviews as review_repository
from app.repositories.assignments import coach_identity

# Jakarta has a fixed UTC+07:00 offset. Avoid requiring OS tzdata on Windows.
JAKARTA = timezone(timedelta(hours=7), name="Asia/Jakarta")


def public_slug(value):
    return "kuda-kuda" if value == "kuda_kuda" else value


def items(db, rows):
    evaluations, media, names = repository.related(db, rows)
    reviews, assigned = review_repository.bundle(db, rows)
    fallback = dict(MOVEMENTS)
    result = []
    for session in rows:
        evaluation = evaluations.get(session.id)
        score = evaluation.score if evaluation and session.processing_status == "completed" else None
        reason = None if score is not None else evaluation.status if evaluation else (
            "analysis_failed" if session.processing_status == "failed" else
            "evaluation_pending" if session.processing_status in {"queued", "processing"} else "evaluation_unavailable")
        review = reviews.get(session.id)
        result.append(HistoryItem(session=session_out(session, evaluation, media.get(session.id), review, session.user_id in assigned),
            movementName=names.get(session.movement, fallback.get(session.movement, session.movement)),
            score=score, scoreReason=reason, review=review))
    return result


def read_history(db, owner_id, query, *, cursor_owner=None, cursor_scope="member-history"):
    filters = query.cursor_filters()
    actor = owner_id if cursor_owner is None else cursor_owner
    position = decode_cursor(query.cursor, actor, filters, scope=cursor_scope) if query.cursor is not None else None
    rows = repository.history_rows(db, owner_id, query, position)
    more = len(rows) > query.limit
    rows = rows[:query.limit]
    cursor = encode_cursor(actor, filters, rows[-1].created_at, rows[-1].id, scope=cursor_scope) if more else None
    return HistoryPage(items=items(db, rows), nextCursor=cursor)


def note_out(row):
    note, author, profile = row
    return PublishedNote(id=str(note.id), author=CoachIdentity(id=str(author.id), fullName=author.name,
        title=profile.title if profile else None), text=note.note, publishedAt=note.created_at)


def read_detail(db, owner_id, value):
    session = get_session(db, owner_id, value)
    evaluations, media, _ = repository.related(db, [session])
    evaluation = evaluations.get(session.id)
    reviews, assigned = review_repository.bundle(db, [session])
    review = reviews.get(session.id)
    return SessionDetail(session=session_out(session, evaluation, media.get(session.id), review, session.user_id in assigned),
        evaluation=evaluation_out(session, evaluation) if evaluation and session.processing_status == "completed" else None,
        coach=coach_identity(db, owner_id), review=review, reviewHistory=review_repository.history(db, session.id),
        followUpTasks=review_repository.tasks(db, session.id),
        legacyNotes=[note_out(row) for row in repository.notes(db, owner_id, session.id)])


def read_dashboard(db, owner_id):
    timestamp = now().replace(tzinfo=timezone.utc)
    local_date = timestamp.astimezone(JAKARTA).date()
    monday = local_date - timedelta(days=local_date.weekday())
    start = datetime.combine(monday, datetime.min.time(), tzinfo=JAKARTA).astimezone(timezone.utc).replace(tzinfo=None)
    end = start + timedelta(days=7)
    days = [DailyActivity(date=(monday + timedelta(days=index)).isoformat(), sessionCount=0, durationSeconds=0)
            for index in range(7)]
    for completed, duration in repository.week_rows(db, owner_id, start, end):
        index = (completed.replace(tzinfo=timezone.utc).astimezone(JAKARTA).date() - monday).days
        days[index].sessionCount += 1
        if duration is not None and isfinite(duration) and duration >= 0:
            days[index].durationSeconds += duration
    counts = dict(repository.movement_counts(db, owner_id))
    # Catalog order resolves ties, even when a category is currently inactive.
    order = repository.movement_order(db)
    ordered = [row.slug for row in order] + [slug for slug, _ in MOVEMENTS if slug not in {row.slug for row in order}]
    dominant = max(ordered, key=lambda slug: counts.get(slug, 0))
    last = repository.last_session(db, owner_id)
    latest_note = repository.notes(db, owner_id, latest=True)
    note = note_out(latest_note) if latest_note else None
    from sqlalchemy import select
    from app.models.entities import ReviewRevision, TrainingSession
    latest_review = db.scalar(select(ReviewRevision).join(TrainingSession, TrainingSession.id == ReviewRevision.session_id)
        .where(TrainingSession.user_id == owner_id, TrainingSession.deleted_at.is_(None),
               ReviewRevision.payload["note"].as_string().is_not(None))
        .order_by(ReviewRevision.created_at.desc(), ReviewRevision.id.desc()).limit(1))
    if latest_review and (not note or (latest_review.created_at, latest_review.id) >=
                         (latest_note[0].created_at, latest_note[0].id)):
        published = latest_review.payload
        note = PublishedNote(id=f"review:{latest_review.id}", author=published["author"],
            text=published["note"], publishedAt=latest_review.created_at)
    return Dashboard(statistics=activity_summary(db, owner_id),
        lastSession=items(db, [last])[0] if last else None,
        latestCoachNote=note, coach=coach_identity(db, owner_id),
        dominantMovementSlug=public_slug(dominant) if counts.get(dominant, 0) else None,
        weeklyActivity=days)
