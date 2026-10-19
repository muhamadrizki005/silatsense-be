from datetime import timedelta, timezone
import hashlib
import hmac
import secrets

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import DomainError
from app.core.security import passwords, token_hash
from app.models.entities import AuthRateBucket, RecoveryToken, RefreshToken, User, now
from app.repositories.profiles import lock_user

GENERIC = {"detail": "Jika memenuhi syarat, instruksi akan dikirim."}


def rate_limit(db: Session, operation: str, identity: str, limit: int, seconds: int):
    timestamp = now()
    bucket = int(timestamp.replace(tzinfo=timezone.utc).timestamp()) // seconds
    digest = hmac.new(
        settings.jwt_secret.encode(),
        f"recovery:{operation}:{identity}:{bucket}".encode(),
        hashlib.sha256,
    ).hexdigest()
    values = dict(
        key_hash=digest, count=0, expires_at=timestamp + timedelta(seconds=seconds)
    )
    if db.bind.dialect.name == "mysql":
        from sqlalchemy.dialects.mysql import insert

        stmt = insert(AuthRateBucket).values(**values)
        db.execute(stmt.on_duplicate_key_update(key_hash=stmt.inserted.key_hash))
    else:
        from sqlalchemy.dialects.sqlite import insert

        db.execute(insert(AuthRateBucket).values(**values).on_conflict_do_nothing())
    result = db.execute(
        update(AuthRateBucket)
        .where(AuthRateBucket.key_hash == digest, AuthRateBucket.count < limit)
        .values(count=AuthRateBucket.count + 1)
    )
    db.commit()  # Failed password/token attempts must also count.
    if result.rowcount != 1:
        raise DomainError(
            429, "rate_limited", "Terlalu banyak percobaan. Coba lagi nanti."
        )


def request_token(db, mail, purpose, data, ip, actor=None):
    identity = str(actor.id) if actor else data.identifier
    rate_limit(db, "request-ip", ip, 20, 3600)
    rate_limit(db, "request-identity", identity, 5, 3600)
    if actor:
        version = actor.auth_version
        user = lock_user(db, actor.id)
        if not user or user.auth_version != version:
            raise DomainError(401, "unauthenticated", "Silakan masuk kembali.")
        if not passwords.verify(data.currentPassword, user.password_hash):
            raise DomainError(
                401, "invalid_current_password", "Kata sandi lama tidak sesuai."
            )
        email = str(data.email) if purpose == "link" else user.email
        if not email:
            raise DomainError(422, "email_not_linked", "Tautkan email terlebih dahulu.")
        if purpose == "link" and db.scalar(
            select(User.id).where(User.email == email, User.id != user.id)
        ):
            db.rollback()
            return GENERIC
    else:
        column = User.email if "@" in data.identifier else User.npm
        uid = db.scalar(select(User.id).where(column == data.identifier))
        user = lock_user(db, uid) if uid else None
        if not user or not user.email or not user.email_verified_at:
            db.rollback()
            return GENERIC
        email = user.email
    raw = secrets.token_urlsafe(48)
    db.execute(
        update(RecoveryToken)
        .where(
            RecoveryToken.user_id == user.id,
            RecoveryToken.purpose == purpose,
            RecoveryToken.used_at.is_(None),
        )
        .values(used_at=now())
    )
    db.add(
        RecoveryToken(
            user_id=user.id,
            token_hash=token_hash(raw),
            purpose=purpose,
            email=email,
            auth_version=user.auth_version,
            expires_at=now() + timedelta(minutes=30)
            if purpose == "reset"
            else now() + timedelta(hours=24),
        )
    )
    db.flush()
    try:
        mail.send(email, purpose, raw)
    except Exception:
        # Never emit exceptions containing recipient, credentials or message/token.
        db.rollback()
        if actor:
            raise DomainError(
                503, "mail_unavailable", "Layanan email sementara tidak tersedia."
            )
        return GENERIC  # Public reset delivery failure must not enumerate accounts.
    db.commit()
    return GENERIC


def invalid():
    return DomainError(
        422, "invalid_or_expired_token", "Token tidak valid atau kedaluwarsa."
    )


def confirm_token(db, purpose, data, ip, actor=None):
    rate_limit(db, "confirm-ip", ip, 10, 900)
    digest = token_hash(data.token)
    uid = db.scalar(
        select(RecoveryToken.user_id).where(RecoveryToken.token_hash == digest)
    )
    authorized_version = actor.auth_version if actor else None
    user = lock_user(db, uid) if uid else None
    row = (
        db.scalar(
            select(RecoveryToken)
            .where(RecoveryToken.token_hash == digest)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if user
        else None
    )
    if (
        not row
        or row.purpose != purpose
        or row.used_at
        or row.expires_at <= now()
        or row.auth_version != user.auth_version
        or (actor and (actor.id != user.id or authorized_version != user.auth_version))
        or (purpose != "link" and row.email != user.email)
        or (purpose == "reset" and not user.email_verified_at)
    ):
        raise invalid()
    if purpose == "reset" and passwords.verify(data.newPassword, user.password_hash):
        raise DomainError(
            422, "password_unchanged", "Gunakan kata sandi baru yang berbeda."
        )
    claimed = db.execute(
        update(RecoveryToken)
        .where(RecoveryToken.id == row.id, RecoveryToken.used_at.is_(None))
        .values(used_at=now())
    )
    if claimed.rowcount != 1:
        db.rollback()
        raise invalid()
    if purpose in {"link", "verify"}:
        user.email = row.email
        user.email_verified_at = now()
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise invalid()
    if purpose in {"link", "reset"}:
        if purpose == "reset":
            user.password_hash = passwords.hash(data.newPassword)
            user.password_changed_at = now()
        user.auth_version += 1
        db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id)
            .values(revoked=True)
        )
        db.execute(
            update(RecoveryToken)
            .where(RecoveryToken.user_id == user.id, RecoveryToken.used_at.is_(None))
            .values(used_at=now())
        )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise invalid()  # Email uniqueness is checked again atomically by the DB.
