from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import member_user
from app.db.session import get_db
from app.models.entities import User
from app.schemas.domain import DomainErrorOut
from app.schemas.history import Dashboard, HistoryPage, HistoryQuery, SessionDetail
from app.services.history import read_dashboard, read_detail, read_history

router = APIRouter(prefix="/api/v1/member", tags=["History and dashboard"], responses={
    code: {"model": DomainErrorOut} for code in (401, 403, 404, 422, 500)
})


@router.get("/history", response_model=HistoryPage)
def history(query: Annotated[HistoryQuery, Query()], user: User = Depends(member_user), db: Session = Depends(get_db)):
    return read_history(db, user.id, query)


@router.get("/history/{session_id}", response_model=SessionDetail)
def detail(session_id: str, user: User = Depends(member_user), db: Session = Depends(get_db)):
    return read_detail(db, user.id, session_id)


@router.get("/dashboard", response_model=Dashboard)
def dashboard(user: User = Depends(member_user), db: Session = Depends(get_db)):
    return read_dashboard(db, user.id)
