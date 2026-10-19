from datetime import datetime, timezone
from typing import Literal

from pydantic import field_serializer

from app.schemas.domain import DomainModel, MovementSlug


class SessionModel(DomainModel):
    @field_serializer("*", check_fields=False)
    def utc_values(self, value):
        if isinstance(value, datetime):
            return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
        return value


class AcceptedSession(SessionModel):
    sessionId: str
    processingStatus: Literal["queued"] = "queued"
    statusUrl: str
    evaluationUrl: str
    uploadedAt: datetime


class MediaOut(SessionModel):
    status: Literal["available", "expired", "deleted", "unavailable"]
    expiresAt: datetime | None
    mimeType: str | None
    byteSize: int | None
    durationSeconds: float | None
    width: int | None
    height: int | None
    playbackPath: str | None


class SessionFailure(DomainModel):
    code: str
    detail: str


class SessionOut(SessionModel):
    id: str
    movementSlug: MovementSlug
    createdAt: datetime
    uploadedAt: datetime | None
    startedAt: datetime | None
    completedAt: datetime | None
    processingStatus: Literal["queued", "processing", "completed", "failed"]
    analysisStatus: str | None
    evaluationId: str | None
    reviewStatus: Literal["pending", "approved", "needs_revision"] = "pending"
    reviewAvailable: bool = False
    retryOf: str | None
    acknowledgedAt: datetime | None
    error: SessionFailure | None
    media: MediaOut
