from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.core.security import passwords
from app.models.entities import CoachProfile, MemberProfile, RefreshToken, User, now
from app.repositories.profiles import activity_summary, lock_user, profile_row
from app.schemas.domain import PasswordChange, ProfileOut


def read_profile(db: Session, user: User) -> ProfileOut:
    from app.repositories.assignments import coach_identity
    from app.models.entities import CoachAssignment
    from sqlalchemy import select
    row = profile_row(db, user)
    member = user.role == "MEMBER"
    return ProfileOut(
        id=str(user.id), role=user.role.lower(), fullName=user.name,
        npm=user.npm, email=user.email, emailVerifiedAt=user.email_verified_at,
        division=row.division if row else None,
        title=row.title if row and not member else None,
        belt=row.belt if row and member else None,
        beltTarget=row.belt_target if row and member else None,
        passwordChangedAt=user.password_changed_at, createdAt=user.created_at,
        coach=coach_identity(db, user.id) if member else None,
        statistics=activity_summary(db, user.id if member else select(CoachAssignment.member_id).where(
            CoachAssignment.coach_id == user.id)),
    )


def patch_profile(db: Session, user: User, data) -> ProfileOut:
    authorized_version = user.auth_version
    user = lock_user(db, user.id)
    if not user or user.auth_version != authorized_version:
        raise DomainError(401, "unauthenticated", "Silakan masuk kembali.")
    fields = data.model_dump(exclude_unset=True)
    if "fullName" in fields:
        user.name = fields.pop("fullName")
    if fields:
        row = profile_row(db, user)
        if row is None:
            row = MemberProfile(user_id=user.id) if user.role == "MEMBER" else CoachProfile(user_id=user.id)
            db.add(row)
        for key, value in fields.items():
            setattr(row, key, value)
    db.commit()
    return read_profile(db, user)


def change_password(db: Session, user: User, data: PasswordChange):
    authorized_version = user.auth_version
    user = lock_user(db, user.id)
    if not user or user.auth_version != authorized_version:
        raise DomainError(401, "unauthenticated", "Silakan masuk kembali.")
    if not passwords.verify(data.currentPassword, user.password_hash):
        raise DomainError(401, "invalid_current_password", "Kata sandi lama tidak sesuai.")
    if passwords.verify(data.newPassword, user.password_hash):
        raise DomainError(422, "password_unchanged", "Gunakan kata sandi baru yang berbeda.")
    user.password_hash = passwords.hash(data.newPassword)
    user.password_changed_at = now()
    user.auth_version += 1
    db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id).values(revoked=True))
    db.commit()
