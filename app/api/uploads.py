from typing import Annotated

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.core.security import check_origin, member_user
from app.db.session import get_db
from app.models.entities import User
from app.schemas.domain import DomainErrorOut
from app.schemas.sessions import AcceptedSession
from app.schemas.uploads import UploadRequest, UploadTicket
from app.services.uploads import complete_upload, initiate_upload

router = APIRouter(
    prefix="/api/v1/member/uploads",
    tags=["Training sessions"],
    dependencies=[Depends(check_origin)],
    responses={
        code: {"model": DomainErrorOut}
        for code in (401, 403, 404, 409, 410, 413, 415, 422, 429, 503)
    },
)


@router.post("", status_code=201, response_model=UploadTicket)
def initiate(
    request: UploadRequest,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=1, max_length=128)
    ],
    user: User = Depends(member_user),
    db: Session = Depends(get_db),
):
    return initiate_upload(db, user, request, idempotency_key)


@router.post("/{upload_id}/complete", status_code=202, response_model=AcceptedSession)
def complete(
    upload_id: str, user: User = Depends(member_user), db: Session = Depends(get_db)
):
    return complete_upload(db, user, upload_id)
