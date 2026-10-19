from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.security import check_origin, current_user
from app.db.session import get_db
from app.models.entities import User
from app.schemas.recovery import (
    RecoveryAccepted,
    EmailLinkRequest,
    Reauthenticate,
    ResetRequest,
    ResetConfirm,
    TokenConfirm,
)
from app.services.mail import get_mail_adapter, MailAdapter
from app.services.recovery import request_token, confirm_token

router = APIRouter(
    prefix="/api/v1/auth",
    tags=["Account recovery"],
    dependencies=[Depends(check_origin)],
)


def ip(request):
    return request.client.host if request.client else "unknown"


@router.post("/email-link/request", status_code=202, response_model=RecoveryAccepted)
def email_link(
    data: EmailLinkRequest,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    mail: MailAdapter = Depends(get_mail_adapter),
):
    return request_token(db, mail, "link", data, ip(request), user)


@router.post(
    "/email-verification/request", status_code=202, response_model=RecoveryAccepted
)
def email_verify(
    data: Reauthenticate,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    mail: MailAdapter = Depends(get_mail_adapter),
):
    return request_token(db, mail, "verify", data, ip(request), user)


@router.post(
    "/password-reset/request", status_code=202, response_model=RecoveryAccepted
)
def reset_request(
    data: ResetRequest,
    request: Request,
    db: Session = Depends(get_db),
    mail: MailAdapter = Depends(get_mail_adapter),
):
    return request_token(db, mail, "reset", data, ip(request))


@router.post("/email-link/confirm", status_code=204)
def link_confirm(
    data: TokenConfirm,
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    confirm_token(db, "link", data, ip(request), user)
    response.delete_cookie("refresh_token", path="/api/v1/auth")


@router.post("/email-verification/confirm", status_code=204)
def verify_confirm(
    data: TokenConfirm,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    confirm_token(db, "verify", data, ip(request), user)


@router.post("/password-reset/confirm", status_code=204)
def reset_confirm(
    data: ResetConfirm,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    confirm_token(db, "reset", data, ip(request))
    response.delete_cookie("refresh_token", path="/api/v1/auth")
