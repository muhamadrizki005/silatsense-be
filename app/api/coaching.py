from typing import Annotated
from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy.orm import Session

from app.core.security import coach_user, member_user, check_origin
from app.db.session import get_db
from app.models.entities import User
from app.repositories.assignments import require_member
from app.schemas.coaching import CoachOverview, CoachSessionDetail, RosterDetail, RosterPage, RosterQuery
from app.schemas.domain import DomainErrorOut
from app.schemas.history import HistoryPage, HistoryQuery
from app.schemas.results import PoseOut
from app.schemas.reviews import DraftInput, DraftOut, PublishInput, PublishedReview, RetryInput, RetryOut, TaskOut, TaskPatch
from app.services import coaching, reviews
from app.services.history import read_history
from app.services.media import playback
from app.services.results import read_pose
from app.services.sessions import identifier

router = APIRouter(prefix="/api/v1", tags=["Coaching and follow-ups"], responses={
    code: {"model": DomainErrorOut} for code in (401, 403, 404, 409, 410, 416, 422, 500)
})
Key = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)]


@router.get("/coach/overview", response_model=CoachOverview)
def overview(user: User = Depends(coach_user), db: Session = Depends(get_db)):
    return coaching.overview(db, user)


@router.get("/coach/roster", response_model=RosterPage)
def roster(query: Annotated[RosterQuery, Query()], user: User = Depends(coach_user), db: Session = Depends(get_db)):
    return coaching.roster(db, user, query)


@router.get("/coach/roster/{member_id}", response_model=RosterDetail)
def member_detail(member_id: str, user: User = Depends(coach_user), db: Session = Depends(get_db)):
    return coaching.roster_detail(db, user, member_id)


@router.get("/coach/roster/{member_id}/sessions", response_model=HistoryPage)
def member_sessions(member_id: str, query: Annotated[HistoryQuery, Query()],
                    user: User = Depends(coach_user), db: Session = Depends(get_db)):
    coach_id, mid = user.id, identifier(member_id)
    db.rollback()
    require_member(db, coach_id, mid, lock=True)
    return read_history(db, mid, query, cursor_owner=coach_id, cursor_scope=f"coach-history:{mid}")


@router.get("/coach/sessions/{session_id}", response_model=CoachSessionDetail)
def session_detail(session_id: str, user: User = Depends(coach_user), db: Session = Depends(get_db)):
    return coaching.session_detail(db, user, session_id)


@router.get("/coach/sessions/{session_id}/pose", response_model=PoseOut)
def pose(session_id: str, user: User = Depends(coach_user), db: Session = Depends(get_db)):
    _, _, session = reviews.coach_gate(db, user, session_id)
    return read_pose(db, session.user_id, str(session.id))


@router.get("/coach/sessions/{session_id}/video", response_class=Response, responses={
    200: {"content": {"video/mp4": {}, "video/quicktime": {}, "video/webm": {}}},
    206: {"description": "Private single byte range", "content": {"video/mp4": {}, "video/quicktime": {}, "video/webm": {}}},
})
def video(session_id: str, range_header: Annotated[str | None, Header(alias="Range")] = None,
          user: User = Depends(coach_user), db: Session = Depends(get_db)):
    user, assignment, session = reviews.coach_gate(db, user, session_id)
    return playback(db, user, session_id, range_header, owner_id=session.user_id, assignment_event_id=assignment.event_id)


@router.put("/coach/sessions/{session_id}/feedback-draft", response_model=DraftOut, dependencies=[Depends(check_origin)])
def draft(session_id: str, data: DraftInput, user: User = Depends(coach_user), db: Session = Depends(get_db)):
    return reviews.save_draft(db, user, session_id, data)


@router.post("/coach/sessions/{session_id}/reviews", status_code=201, response_model=PublishedReview, dependencies=[Depends(check_origin)])
def publish(session_id: str, data: PublishInput, idempotency_key: Key,
            user: User = Depends(coach_user), db: Session = Depends(get_db)):
    return reviews.publish(db, user, session_id, data, idempotency_key)


@router.post("/member/sessions/{session_id}/follow-ups", status_code=201, response_model=RetryOut, dependencies=[Depends(check_origin)])
def retry(session_id: str, data: RetryInput, idempotency_key: Key,
          user: User = Depends(member_user), db: Session = Depends(get_db)):
    return reviews.retry_intent(db, user, session_id, data, idempotency_key)


@router.patch("/member/follow-up-tasks/{task_id}", response_model=TaskOut, dependencies=[Depends(check_origin)])
def task(task_id: str, data: TaskPatch, user: User = Depends(member_user), db: Session = Depends(get_db)):
    return reviews.patch_task(db, user, task_id, data)
