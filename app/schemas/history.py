from datetime import datetime, timezone
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.schemas.domain import ActivitySummary, CoachIdentity, DomainModel, MovementSlug
from app.schemas.results import EvaluationOut
from app.schemas.sessions import SessionModel, SessionOut
from app.schemas.reviews import PublishedReview, TaskOut


class HistoryQuery(DomainModel):
    limit: int = Field(default=20, ge=1, le=100)
    # Decode validates the bound so all malformed cursors share invalid_cursor.
    cursor: str | None = Field(default=None, json_schema_extra={"maxLength": 4096})
    movementSlug: MovementSlug | None = None
    processingStatus: Literal["queued", "processing", "completed", "failed"] | None = None
    reviewStatus: Literal["pending", "needs_revision", "approved"] | None = None
    fromAt: datetime | None = Field(default=None, alias="from")
    toAt: datetime | None = Field(default=None, alias="to")

    @field_validator("fromAt", "toAt", mode="before")
    @classmethod
    def utc_filter(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            if "T" not in value:
                raise ValueError("Gunakan timestamp ISO 8601 UTC.")
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset().total_seconds() != 0:
            raise ValueError("Timestamp harus UTC dengan Z atau +00:00.")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def ordered_dates(self):
        if self.fromAt is not None and self.toAt is not None and self.fromAt >= self.toAt:
            raise ValueError("from harus lebih kecil dari to.")
        return self

    def cursor_filters(self):
        return self.model_dump(mode="json", by_alias=True, exclude={"cursor", "limit"})


class PublishedNote(SessionModel):
    id: str
    author: CoachIdentity
    text: str
    publishedAt: datetime


class HistoryItem(DomainModel):
    session: SessionOut
    movementName: str
    score: float | None = Field(allow_inf_nan=False)
    scoreReason: str | None
    review: PublishedReview | None = None


class HistoryPage(DomainModel):
    items: list[HistoryItem]
    nextCursor: str | None


class SessionDetail(DomainModel):
    session: SessionOut
    evaluation: EvaluationOut | None
    coach: CoachIdentity | None = None
    review: PublishedReview | None = None
    reviewHistory: list[PublishedReview] = Field(default_factory=list)
    legacyNotes: list[PublishedNote]
    followUpTasks: list[TaskOut] = Field(default_factory=list)


class DailyActivity(DomainModel):
    date: str
    sessionCount: int
    durationSeconds: float


class Dashboard(DomainModel):
    statistics: ActivitySummary
    lastSession: HistoryItem | None
    latestCoachNote: PublishedNote | None
    coach: CoachIdentity | None = None
    dominantMovementSlug: MovementSlug | None
    weeklyActivity: list[DailyActivity]
    timezone: Literal["Asia/Jakarta"] = "Asia/Jakarta"
