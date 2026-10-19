from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.routes import router
from app.api.profile import router as profile_router
from app.api.training import router as training_router
from app.core.errors import install_domain_errors
from app.api.sessions import router as sessions_router
from app.api.history import router as history_router
from app.api.coaching import router as coaching_router
from app.core.upload_limits import UploadBodyLimit
from app.api.recovery import router as recovery_router
from app.api.health import router as health_router
from app.core.observability import RequestLogMiddleware

app = FastAPI(title="SilatSense Backend", version="0.7.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "PUT"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "Range"],
    expose_headers=["Accept-Ranges", "Content-Range", "X-Request-ID"],
)
app.include_router(router)
app.include_router(profile_router)
app.include_router(training_router)
app.include_router(sessions_router)
app.include_router(history_router)
app.include_router(coaching_router)
app.include_router(recovery_router)
app.include_router(health_router)
app.add_middleware(UploadBodyLimit)
install_domain_errors(app)
app.add_middleware(RequestLogMiddleware)


@app.get("/health")
def health():
    return {"status": "ok", "application": "SilatSense", "mode": "experimental"}
