from sqlalchemy import and_, func, or_, select

from app.core.cursors import decode_cursor, encode_cursor
from app.models.entities import CoachAssignment, EvaluationIssue, EvaluationSession, ReviewHead, TrainingSession, User
from app.repositories.assignments import require_member
from app.repositories.profiles import activity_summary
from app.repositories.history import last_session
from app.schemas.coaching import CoachOverview, CoachSessionDetail, RosterDetail, RosterMember, RosterPage
from app.services.history import items, read_detail
from app.services.profiles import read_profile
from app.services.reviews import coach_gate, draft_out, draft_row
from app.services.sessions import identifier


def scope(coach_id):
    return select(CoachAssignment.member_id).where(CoachAssignment.coach_id == coach_id)


def roster(db, actor, query):
    filters = {"q": query.q}
    position = decode_cursor(query.cursor, actor.id, filters, scope="coach-roster") if query.cursor is not None else None
    statement = select(User).where(User.id.in_(scope(actor.id)), User.role == "MEMBER")
    if query.q:
        # Literal substring, not user-controlled SQL LIKE wildcards.
        statement = statement.where(or_(User.name.contains(query.q, autoescape=True),
            User.npm.contains(query.q, autoescape=True), User.email.contains(query.q, autoescape=True)))
    if position:
        time, uid = position
        statement = statement.where(or_(User.created_at < time, and_(User.created_at == time, User.id < uid)))
    rows = db.scalars(statement.order_by(User.created_at.desc(), User.id.desc()).limit(query.limit + 1)).all()
    more, rows = len(rows) > query.limit, rows[:query.limit]
    next_cursor = encode_cursor(actor.id, filters, rows[-1].created_at, rows[-1].id, scope="coach-roster") if more else None
    result = []
    for member in rows:
        last = last_session(db, member.id)
        result.append(RosterMember(profile=read_profile(db, member), latestSession=items(db, [last])[0] if last else None))
    return RosterPage(items=result, nextCursor=next_cursor)


def roster_detail(db, actor, value):
    coach_id, mid = actor.id, identifier(value)
    db.rollback()
    member, _ = require_member(db, coach_id, mid, lock=True)
    profile = read_profile(db, member)
    last = last_session(db, member.id)
    return RosterDetail(profile=profile, statistics=profile.statistics, latestSession=items(db, [last])[0] if last else None)


def session_detail(db, actor, value):
    user, assignment, session = coach_gate(db, actor, value)
    detail = read_detail(db, session.user_id, str(session.id))
    draft = draft_row(db, session.id, assignment)
    return CoachSessionDetail(**detail.model_dump(), feedbackDraft=draft_out(db, draft, user) if draft else None)


def overview(db, actor):
    members = scope(actor.id)
    visible = (TrainingSession.user_id.in_(members), TrainingSession.deleted_at.is_(None))
    count = db.scalar(select(func.count()).select_from(CoachAssignment).where(CoachAssignment.coach_id == actor.id))
    queue = db.scalar(select(func.count()).select_from(TrainingSession).where(*visible,
        TrainingSession.processing_status == "completed", TrainingSession.id.not_in(select(ReviewHead.session_id))))
    rows = db.scalars(select(TrainingSession).where(*visible)
        .order_by(TrainingSession.created_at.desc(), TrainingSession.id.desc()).limit(5)).all()
    issues = db.execute(select(EvaluationIssue.feature, func.count(func.distinct(TrainingSession.id)).label("samples"))
        .join(EvaluationSession, EvaluationSession.id == EvaluationIssue.evaluation_id)
        .join(TrainingSession, TrainingSession.id == EvaluationSession.training_session_id)
        .where(*visible, TrainingSession.processing_status == "completed")
        .group_by(EvaluationIssue.feature).order_by(func.count(func.distinct(TrainingSession.id)).desc(),
            EvaluationIssue.feature).limit(6)).all()
    return CoachOverview(memberCount=count, reviewQueueCount=queue, statistics=activity_summary(db, members),
        recentSessions=items(db, rows), topIssues=[dict(feature=feature, sessionCount=samples) for feature, samples in issues])
