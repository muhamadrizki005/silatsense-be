from datetime import datetime, timedelta, timezone
import hashlib
import secrets
import jwt
from pwdlib import PasswordHash
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.core.config import settings
from app.db.session import get_db
from app.models.entities import User, RefreshToken, now
from app.repositories.profiles import lock_user

passwords = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)
ACCESS_TOKEN_SECONDS = 900


def token_hash(token: str):
    return hashlib.sha256(token.encode()).hexdigest()


def issue_tokens(db: Session, user: User, *, persistent=True, expires_at=None):
    user = lock_user(db, user.id)
    if user is None:
        raise HTTPException(401, "Silakan masuk kembali.")
    access = jwt.encode(
        {
            "sub": str(user.id),
            "type": "access",
            "jti": secrets.token_hex(16),
            "authVersion": user.auth_version,
            "exp": datetime.now(timezone.utc) + timedelta(seconds=ACCESS_TOKEN_SECONDS),
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    refresh = secrets.token_urlsafe(48)
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=token_hash(refresh),
            expires_at=expires_at or now() + timedelta(days=7 if persistent else 1),
            persistent=persistent,
            auth_version=user.auth_version,
        )
    )
    db.commit()
    return access, refresh


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
):
    try:
        if not credentials:
            raise ValueError()
        payload = jwt.decode(
            credentials.credentials, settings.jwt_secret, algorithms=["HS256"],
            options={"require": ["exp", "sub", "type"]},
        )
        if payload.get("type") != "access":
            raise ValueError()
        user = db.get(User, int(payload["sub"]))
        version = payload.get("authVersion", 0)
        if not user or type(version) is not int or version != user.auth_version:
            raise ValueError()
        return user
    except (jwt.PyJWTError, ValueError, KeyError, TypeError):
        raise HTTPException(401, "Silakan masuk kembali.")


def coach_user(user: User = Depends(current_user)):
    if user.role != "COACH":
        raise HTTPException(403, "Akses khusus pelatih.")
    return user


def member_user(user: User = Depends(current_user)):
    if user.role != "MEMBER":
        raise HTTPException(403, "Akses khusus Member.")
    return user


def check_origin(request: Request):
    origin = request.headers.get("origin")
    if origin and origin != settings.frontend_origin:
        raise HTTPException(403, "Origin tidak diizinkan.")


def auth_request_rate(request: Request, db: Session = Depends(get_db)):
    from app.services.recovery import rate_limit
    ip = request.client.host if request.client else "unknown"
    signup = request.url.path.endswith(("/register", "/sign-up"))
    rate_limit(db, "signup-ip" if signup else "auth-ip", ip,
               settings.signup_ip_requests_per_hour if signup else settings.auth_ip_requests_per_15_minutes,
               3600 if signup else 900)
