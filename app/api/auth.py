from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    ACCESS_TOKEN_SECONDS,
    auth_request_rate,
    check_origin,
    current_user,
    issue_tokens,
    token_hash,
)
from app.db.session import get_db
from app.models.entities import RefreshToken, User, now
from app.repositories.profiles import lock_user
from app.schemas.auth import AuthTokens, AuthUser, SignIn, SignUp
from app.services.auth import authenticate, create_user, frontend_user

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


def token_response(db, user, response, *, persistent=False, expires_at=None):
    access, refresh = issue_tokens(
        db, user, persistent=persistent, expires_at=expires_at
    )
    max_age = None
    if persistent:
        max_age = (
            max(0, int((expires_at - now()).total_seconds())) if expires_at else 604800
        )
    response.set_cookie(
        "refresh_token",
        refresh,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        max_age=max_age,
        path="/api/v1/auth",
    )
    response.headers["Cache-Control"] = "no-store"
    return {
        "accessToken": access,
        "expiresIn": ACCESS_TOKEN_SECONDS,
        "user": frontend_user(user),
    }


@router.post(
    "/sign-up",
    status_code=201,
    response_model=AuthTokens,
    dependencies=[Depends(check_origin), Depends(auth_request_rate)],
)
def sign_up(data: SignUp, response: Response, db: Session = Depends(get_db)):
    user = create_user(db, data.fullName, data.identifier, data.password)
    return token_response(db, user, response)


@router.post(
    "/sign-in",
    response_model=AuthTokens,
    dependencies=[Depends(check_origin), Depends(auth_request_rate)],
)
def sign_in(data: SignIn, response: Response, db: Session = Depends(get_db)):
    user = authenticate(db, data.identifier, data.password)
    return token_response(db, user, response, persistent=data.rememberMe)


@router.get("/session", response_model=AuthUser)
def auth_session(response: Response, user: User = Depends(current_user)):
    response.headers["Cache-Control"] = "no-store"
    return frontend_user(user)


@router.post(
    "/refresh-session",
    response_model=AuthTokens,
    dependencies=[Depends(check_origin), Depends(auth_request_rate)],
)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    digest = token_hash(request.cookies.get("refresh_token", ""))
    # Lock the owner before the refresh token to serialize with password changes.
    owner_id = db.scalar(
        select(RefreshToken.user_id).where(RefreshToken.token_hash == digest)
    )
    user = lock_user(db, owner_id) if owner_id is not None else None
    row = (
        db.scalar(
            select(RefreshToken)
            .where(RefreshToken.token_hash == digest)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if user
        else None
    )
    if (
        not row
        or row.revoked
        or row.expires_at <= now()
        or row.auth_version != user.auth_version
    ):
        raise HTTPException(401, "Sesi berakhir. Silakan masuk kembali.")
    claimed = db.execute(
        update(RefreshToken)
        .where(RefreshToken.id == row.id, RefreshToken.revoked.is_(False))
        .values(revoked=True)
    )
    if claimed.rowcount != 1:
        db.rollback()
        raise HTTPException(401, "Token sudah digunakan.")
    return token_response(
        db, user, response, persistent=row.persistent, expires_at=row.expires_at
    )


@router.post("/logout", status_code=204, dependencies=[Depends(check_origin)])
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.token_hash
            == token_hash(request.cookies.get("refresh_token", ""))
        )
        .values(revoked=True)
    )
    db.commit()
    response.delete_cookie("refresh_token", path="/api/v1/auth")
    response.headers["Cache-Control"] = "no-store"
