from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.security import check_origin, coach_user, member_user
from app.db.session import get_db
from app.models.entities import User
from app.schemas.domain import CoachProfilePatch, DomainErrorOut, MemberProfilePatch, PasswordChange, ProfileOut
from app.services.profiles import change_password, patch_profile, read_profile

router = APIRouter(prefix="/api/v1", tags=["Account profile"], responses={
    code: {"model": DomainErrorOut} for code in (401, 403, 422, 500)
})


@router.get("/member/profile", response_model=ProfileOut)
def member_profile(user: User = Depends(member_user), db: Session = Depends(get_db)):
    return read_profile(db, user)


@router.get("/coach/profile", response_model=ProfileOut)
def coach_profile(user: User = Depends(coach_user), db: Session = Depends(get_db)):
    return read_profile(db, user)


@router.patch("/member/profile", response_model=ProfileOut, dependencies=[Depends(check_origin)])
def update_member_profile(data: MemberProfilePatch, user: User = Depends(member_user), db: Session = Depends(get_db)):
    return patch_profile(db, user, data)


@router.patch("/coach/profile", response_model=ProfileOut, dependencies=[Depends(check_origin)])
def update_coach_profile(data: CoachProfilePatch, user: User = Depends(coach_user), db: Session = Depends(get_db)):
    return patch_profile(db, user, data)


def password_result(data, user, db):
    change_password(db, user, data)
    response = Response(status_code=204)
    response.delete_cookie("refresh_token", path="/api/v1/auth")
    return response


@router.patch("/member/password", status_code=204, dependencies=[Depends(check_origin)])
def member_password(data: PasswordChange, user: User = Depends(member_user), db: Session = Depends(get_db)):
    return password_result(data, user, db)


@router.patch("/coach/password", status_code=204, dependencies=[Depends(check_origin)])
def coach_password(data: PasswordChange, user: User = Depends(coach_user), db: Session = Depends(get_db)):
    return password_result(data, user, db)
