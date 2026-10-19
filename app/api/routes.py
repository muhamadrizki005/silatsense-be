from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Response,
    Request,
    UploadFile,
    File,
    Form,
    Query,
)
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.entities import (
    User,
    RefreshToken,
    Movement,
    EvaluationSession,
    CoachNote,
    now,
)
from app.schemas.api import Register, Credentials, UserOut, ProfilePatch, NoteCreate
from app.schemas.api import TokenOut, MovementOut, EvaluationOut, NoteOut
from app.core.security import (
    issue_tokens,
    current_user,
    coach_user,
    member_user,
    token_hash,
    check_origin,
    auth_request_rate,
)
from app.core.config import settings
from app.repositories.evaluations import EvaluationRepository, serialize, is_deleted
from app.services.uploads import evaluate_upload
from app.schemas.auth import SignIn, SignUp, AuthTokens, AuthUser
from app.services.auth import create_user, authenticate, frontend_user
from app.core.security import ACCESS_TOKEN_SECONDS
from app.repositories.profiles import lock_user
from app.repositories.assignments import require_member
from app.models.entities import CoachAssignment

router = APIRouter(prefix="/api/v1")


def token_response(db, user, response, *, persistent=True, expires_at=None, frontend=False):
    access, refresh = issue_tokens(db, user, persistent=persistent, expires_at=expires_at)
    max_age = None
    if persistent:
        max_age = max(0, int((expires_at - now()).total_seconds())) if expires_at else 604800
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
    if frontend:
        return {
            "accessToken": access,
            "expiresIn": ACCESS_TOKEN_SECONDS,
            "user": frontend_user(user),
        }
    return {
        "access_token": access,
        "token_type": "bearer",
        "user": UserOut.model_validate(user),
    }


@router.post(
    "/auth/register", status_code=201, response_model=TokenOut, tags=["Authentication"],
    dependencies=[Depends(auth_request_rate)]
)
def register(data: Register, response: Response, db: Session = Depends(get_db)):
    user = create_user(db, data.name, str(data.email), data.password)
    return token_response(db, user, response)


@router.post("/auth/login", response_model=TokenOut, tags=["Authentication"], dependencies=[Depends(auth_request_rate)])
def login(data: Credentials, response: Response, db: Session = Depends(get_db)):
    user = authenticate(db, str(data.email), data.password)
    return token_response(db, user, response)


@router.post("/auth/sign-up", status_code=201, response_model=AuthTokens,
             tags=["Authentication"], dependencies=[Depends(check_origin), Depends(auth_request_rate)])
def sign_up(data: SignUp, response: Response, db: Session = Depends(get_db)):
    user = create_user(db, data.fullName, data.identifier, data.password)
    return token_response(db, user, response, persistent=False, frontend=True)


@router.post("/auth/sign-in", response_model=AuthTokens,
             tags=["Authentication"], dependencies=[Depends(check_origin), Depends(auth_request_rate)])
def sign_in(data: SignIn, response: Response, db: Session = Depends(get_db)):
    user = authenticate(db, data.identifier, data.password)
    return token_response(db, user, response, persistent=data.rememberMe, frontend=True)


@router.get("/auth/session", response_model=AuthUser, tags=["Authentication"])
def auth_session(response: Response, user: User = Depends(current_user)):
    response.headers["Cache-Control"] = "no-store"
    return frontend_user(user)


@router.post(
    "/auth/refresh-session",
    response_model=AuthTokens,
    tags=["Authentication"],
    dependencies=[Depends(check_origin), Depends(auth_request_rate)],
)
@router.post(
    "/auth/refresh",
    response_model=TokenOut,
    tags=["Authentication"],
    dependencies=[Depends(check_origin), Depends(auth_request_rate)],
)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    digest = token_hash(request.cookies.get("refresh_token", ""))
    # Identify owner first; always lock user before refresh to serialize with
    # password changes. Locking reads refresh any repeatable-read snapshot.
    owner_id = db.scalar(select(RefreshToken.user_id).where(RefreshToken.token_hash == digest))
    user = lock_user(db, owner_id) if owner_id is not None else None
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == digest)
                    .with_for_update().execution_options(populate_existing=True)) if user else None
    if not row or row.revoked or row.expires_at <= now() or row.auth_version != user.auth_version:
        raise HTTPException(401, "Sesi berakhir. Silakan masuk kembali.")
    claimed = db.execute(
        update(RefreshToken)
        .where(RefreshToken.id == row.id, RefreshToken.revoked.is_(False))
        .values(revoked=True)
    )
    if claimed.rowcount != 1:
        db.rollback()
        raise HTTPException(401, "Token sudah digunakan.")
    return token_response(db, user, response,
                          persistent=row.persistent, expires_at=row.expires_at,
                          frontend=request.url.path.endswith("/refresh-session"))


@router.post(
    "/auth/logout",
    status_code=204,
    tags=["Authentication"],
    dependencies=[Depends(check_origin)],
)
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


@router.get("/auth/me", response_model=UserOut, tags=["Authentication"])
@router.get("/profile", response_model=UserOut, tags=["Profile"])
def me(response: Response, user: User = Depends(current_user)):
    response.headers["Cache-Control"] = "no-store"
    return user


@router.patch("/profile", response_model=UserOut, tags=["Profile"])
def profile(
    data: ProfilePatch,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    user.name = data.name
    db.commit()
    return user


@router.get("/movements", response_model=list[MovementOut], tags=["Movements"])
def movements(db: Session = Depends(get_db)):
    repository = EvaluationRepository(db)
    return [
        {
            "slug": m.slug,
            "name": m.name,
            "reference_ready": bool(repository.profiles(m.slug)),
        }
        for m in db.scalars(select(Movement).where(Movement.active.is_(True))).all()
    ]


@router.post(
    "/evaluations", status_code=201, response_model=EvaluationOut, tags=["Evaluations"]
)
def evaluate(
    movement_type: str = Form(...),
    video: UploadFile = File(...),
    user: User = Depends(member_user),
    db: Session = Depends(get_db),
):
    if not db.scalar(
        select(Movement).where(
            Movement.slug == movement_type, Movement.active.is_(True)
        )
    ):
        video.file.close()
        raise HTTPException(422, "Kategori gerakan tidak tersedia.")
    return serialize(evaluate_upload(db, user, movement_type, video))


@router.get("/evaluations", response_model=list[EvaluationOut], tags=["Evaluations"])
def history(
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return [
        serialize(e) for e in EvaluationRepository(db).history(user.id, offset, limit)
    ]


@router.get(
    "/evaluations/{evaluation_id}", response_model=EvaluationOut, tags=["Evaluations"]
)
def detail(
    evaluation_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    row = db.get(EvaluationSession, evaluation_id)
    if not row or (user.role != "COACH" and row.user_id != user.id) or is_deleted(db, row):
        raise HTTPException(404, "Evaluasi tidak ditemukan.")
    if user.role == "COACH":
        coach_id, owner_id, row_id = user.id, row.user_id, row.id
        db.rollback()
        require_member(db, coach_id, owner_id, lock=True)
        row = db.get(EvaluationSession, row_id)
        if is_deleted(db, row):
            raise HTTPException(404, "Evaluasi tidak ditemukan.")
    return serialize(row)


@router.get("/coach/members", response_model=list[UserOut], tags=["Coach"])
def members(
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    coach: User = Depends(coach_user),
    db: Session = Depends(get_db),
):
    return db.scalars(
        select(User)
        .where(User.role == "MEMBER")
        .where(User.id.in_(select(CoachAssignment.member_id).where(CoachAssignment.coach_id == coach.id)))
        .order_by(User.id)
        .offset(offset)
        .limit(limit)
    ).all()


def find_member(db, member_id):
    member = db.get(User, member_id)
    if not member or member.role != "MEMBER":
        raise HTTPException(404, "Member tidak ditemukan.")
    return member


@router.get("/coach/members/{member_id}", response_model=UserOut, tags=["Coach"])
def member(
    member_id: int, coach: User = Depends(coach_user), db: Session = Depends(get_db)
):
    coach_id = coach.id
    db.rollback()
    return require_member(db, coach_id, member_id, lock=True)[0]


@router.get(
    "/coach/members/{member_id}/evaluations",
    response_model=list[EvaluationOut],
    tags=["Coach"],
)
def member_history(
    member_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    coach: User = Depends(coach_user),
    db: Session = Depends(get_db),
):
    coach_id = coach.id
    db.rollback()
    require_member(db, coach_id, member_id, lock=True)
    return [
        serialize(e) for e in EvaluationRepository(db).history(member_id, offset, limit)
    ]


@router.post(
    "/coach/evaluations/{evaluation_id}/notes",
    status_code=201,
    response_model=NoteOut,
    tags=["Coach"],
)
def note(
    evaluation_id: int,
    data: NoteCreate,
    coach: User = Depends(coach_user),
    db: Session = Depends(get_db),
):
    evaluation = db.get(EvaluationSession, evaluation_id)
    if not evaluation or is_deleted(db, evaluation):
        raise HTTPException(404, "Evaluasi tidak ditemukan.")
    coach_id, owner_id, authorized_version = coach.id, evaluation.user_id, coach.auth_version
    db.rollback()
    require_member(db, coach_id, owner_id, lock=True)
    coach = lock_user(db, coach_id)
    if not coach or coach.auth_version != authorized_version or coach.role != "COACH":
        raise HTTPException(401, "Silakan masuk kembali.")
    evaluation = db.get(EvaluationSession, evaluation_id)
    if is_deleted(db, evaluation):
        raise HTTPException(404, "Evaluasi tidak ditemukan.")
    row = CoachNote(evaluation_id=evaluation_id, coach_id=coach.id, note=data.note)
    db.add(row)
    db.commit()
    return {
        "id": row.id,
        "note": row.note,
        "coach_name": coach.name,
        "created_at": row.created_at.isoformat() + "Z",
    }
