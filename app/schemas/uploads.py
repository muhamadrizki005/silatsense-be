from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.domain import MovementSlug
from app.schemas.sessions import AcceptedSession, SessionModel


class UploadRequest(SessionModel):
    movementSlug: MovementSlug
    filename: str = Field(min_length=1, max_length=255)
    mimeType: Literal["video/mp4", "video/quicktime", "video/webm"]
    byteSize: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    retryOf: str | None = None


class UploadTicket(SessionModel):
    uploadId: str
    uploadUrl: str | None
    method: Literal["PUT"] = "PUT"
    headers: dict[str, str]
    expiresAt: datetime
    completePath: str
    acceptedSession: AcceptedSession | None = None
