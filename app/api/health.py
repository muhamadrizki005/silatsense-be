from pathlib import Path
import tempfile

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse

from app.core.config import settings
from app.db.session import get_db

router = APIRouter(tags=["Operations"])


@router.get("/health/live")
def live():
    return {"status": "ok"}


@router.get("/health/ready")
def ready(db: Session = Depends(get_db)):
    components = {}
    try:
        db.execute(text("SELECT 1"))
        revisions = set(
            db.execute(text("SELECT version_num FROM alembic_version")).scalars()
        )
        components["database"] = "ok" if revisions == {"0007"} else "migration_required"
    except Exception:
        components["database"] = "unavailable_or_unmigrated"
    try:
        root = Path(settings.media_root)
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=root) as probe:
            probe.write(b"readiness")
            probe.flush()
        components["storage"] = "ok"
    except OSError:
        components["storage"] = "unavailable"
    ok = all(value == "ok" for value in components.values())
    return JSONResponse(
        {"status": "ready" if ok else "not_ready", "components": components},
        status_code=200 if ok else 503,
        headers={"Cache-Control": "no-store"},
    )
