from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import member_user
from app.db.session import get_db
from app.models.entities import User
from app.schemas.domain import DomainErrorOut, TrainingCatalog, TrainingPrep, UploadConfig
from app.services.training import catalog, preparation, upload_config

router = APIRouter(prefix="/api/v1/member", tags=["Training catalog"],
                   dependencies=[Depends(member_user)], responses={
                       code: {"model": DomainErrorOut} for code in (401, 403, 404, 422, 500)
                   })


@router.get("/training-modules", response_model=TrainingCatalog)
def modules(user: User = Depends(member_user), db: Session = Depends(get_db)):
    return catalog(db, user)


@router.get("/training-prep/{slug}", response_model=TrainingPrep)
def prep(slug: str, db: Session = Depends(get_db)):
    return preparation(db, slug)


@router.get("/record-config/{slug}", response_model=UploadConfig)
def record_config(slug: str, db: Session = Depends(get_db)):
    return upload_config(db, slug)
