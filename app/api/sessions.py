from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, UploadFile, Response
from sqlalchemy.orm import Session

from app.core.security import check_origin, member_user
from app.db.session import get_db
from app.models.entities import User
from app.schemas.domain import DomainErrorOut
from app.schemas.sessions import AcceptedSession, SessionOut
from app.services.sessions import accept_upload, read_session
from app.schemas.results import AcknowledgedOut, EvaluationOut, PoseOut
from app.services.results import acknowledge, delete_session, read_evaluation, read_pose
from app.services.media import playback

router = APIRouter(prefix="/api/v1/member/sessions", tags=["Training sessions"], responses={
    code: {"model": DomainErrorOut} for code in (401, 403, 404, 409, 410, 413, 415, 416, 422, 429, 500, 503)
})


@router.post("", status_code=202, response_model=AcceptedSession, dependencies=[Depends(check_origin)])
def upload_session(
    movementSlug: Annotated[str, Form()], video: Annotated[UploadFile, File()],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
    retryOf: Annotated[str | None, Form()] = None,
    user: User = Depends(member_user), db: Session = Depends(get_db),
):
    return accept_upload(db, user, movementSlug, video, idempotency_key, retryOf)


@router.get("/{session_id}", response_model=SessionOut)
def session_status(session_id: str, user: User = Depends(member_user), db: Session = Depends(get_db)):
    return read_session(db, user.id, session_id)


@router.get("/{session_id}/evaluation", response_model=EvaluationOut)
def evaluation(session_id: str, user: User = Depends(member_user), db: Session = Depends(get_db)):
    return read_evaluation(db, user.id, session_id)


@router.get("/{session_id}/pose", response_model=PoseOut)
def pose(session_id: str, user: User = Depends(member_user), db: Session = Depends(get_db)):
    return read_pose(db, user.id, session_id)


@router.get("/{session_id}/video", response_class=Response, responses={
    200: {"content": {"video/mp4": {}, "video/quicktime": {}, "video/webm": {}}},
    206: {"description": "Single byte range", "content": {"video/mp4": {}, "video/quicktime": {}, "video/webm": {}}},
})
def video(session_id: str, range_header: Annotated[str | None, Header(alias="Range")] = None,
          user: User = Depends(member_user), db: Session = Depends(get_db)):
    return playback(db, user, session_id, range_header)


@router.post("/{session_id}/acknowledge", response_model=AcknowledgedOut, dependencies=[Depends(check_origin)])
def acknowledge_session(session_id: str, user: User = Depends(member_user), db: Session = Depends(get_db)):
    return acknowledge(db, user, session_id)


@router.delete("/{session_id}", status_code=204, dependencies=[Depends(check_origin)])
def remove_session(session_id: str, user: User = Depends(member_user), db: Session = Depends(get_db)):
    delete_session(db, user, session_id)
    return Response(status_code=204)
