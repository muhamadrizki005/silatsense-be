from sqlalchemy import select

from app.core.errors import DomainError
from app.models.entities import CoachAssignment, CoachProfile, User
from app.repositories.profiles import lock_user
from app.schemas.domain import CoachIdentity


def current_assignment(db, member_id):
    return db.get(CoachAssignment, member_id)


def coach_identity(db, member_id):
    row = db.execute(select(User, CoachProfile).join(CoachAssignment, CoachAssignment.coach_id == User.id)
        .outerjoin(CoachProfile, CoachProfile.user_id == User.id)
        .where(CoachAssignment.member_id == member_id)).first()
    return identity(row[0], row[1]) if row else None


def identity(user, profile=None):
    return CoachIdentity(id=str(user.id), fullName=user.name, title=profile.title if profile else None)


def require_member(db, coach_id, member_id, *, lock=False):
    # Member is the common serialization gate for transfer, publish and reads.
    member = lock_user(db, member_id) if lock else db.get(User, member_id)
    assignment = db.scalar(select(CoachAssignment).where(CoachAssignment.member_id == member_id)
        .execution_options(populate_existing=True))
    if not member or member.role != "MEMBER" or not assignment or assignment.coach_id != coach_id:
        raise DomainError(404, "not_found", "Member tidak ditemukan dalam binaan.")
    return member, assignment
