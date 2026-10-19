from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import passwords
from app.models.entities import User
from app.schemas.auth import AuthUser


def create_user(db: Session, name: str, identifier: str, password: str) -> User:
    user = User(
        name=name,
        email=identifier if "@" in identifier else None,
        npm=identifier if "@" not in identifier else None,
        role="MEMBER",
        password_hash=passwords.hash(password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "NPM atau email sudah terdaftar.")
    return user


def authenticate(db: Session, identifier: str, password: str) -> User:
    from app.core.config import settings
    from app.services.recovery import rate_limit
    rate_limit(db, "login-identity", identifier, settings.auth_attempts_per_15_minutes, 900)
    column = User.email if "@" in identifier else User.npm
    user = db.scalar(select(User).where(column == identifier).with_for_update()
                     .execution_options(populate_existing=True))
    if not user or not passwords.verify(password, user.password_hash):
        raise HTTPException(401, "NPM/email atau kata sandi tidak sesuai.")
    return user


def frontend_user(user: User) -> AuthUser:
    return AuthUser(
        id=str(user.id), fullName=user.name,
        identifier=user.email or user.npm, role=user.role.lower(),
    )
