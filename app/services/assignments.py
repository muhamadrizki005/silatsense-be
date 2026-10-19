from sqlalchemy import select
from app.core.errors import DomainError
from app.models.entities import AssignmentEvent, CoachAssignment, User, now
from app.repositories.profiles import lock_user


def assign_coach(db, member_id, coach_id, actor, reason):
    actor, reason = actor.strip(), reason.strip()
    if not 1 <= len(actor) <= 120 or not 1 <= len(reason) <= 2000:
        raise DomainError(422, "validation_error", "Actor/reason wajib dan harus sesuai batas panjang.")
    member = lock_user(db, member_id)
    if not member or member.role != "MEMBER":
        raise DomainError(404, "not_found", "Member tidak ditemukan.")
    if coach_id is not None:
        coach = db.get(User, coach_id)
        if not coach or coach.role != "COACH":
            raise DomainError(422, "validation_error", "Coach tidak valid.")
    assignment = db.scalar(select(CoachAssignment).where(CoachAssignment.member_id == member_id)
        .with_for_update().execution_options(populate_existing=True))
    old = assignment.coach_id if assignment else None
    if old == coach_id:
        db.commit()
        return None  # Idempotent no-op, no fabricated change event.
    timestamp = now()
    change = AssignmentEvent(member_id=member_id, from_coach_id=old, to_coach_id=coach_id,
                             actor=actor, reason=reason, created_at=timestamp)
    db.add(change)
    db.flush()
    if coach_id is None:
        db.delete(assignment)
    elif assignment:
        assignment.coach_id, assignment.event_id, assignment.assigned_at = coach_id, change.id, timestamp
    else:
        db.add(CoachAssignment(member_id=member_id, coach_id=coach_id, event_id=change.id, assigned_at=timestamp))
    db.commit()
    return change.id
