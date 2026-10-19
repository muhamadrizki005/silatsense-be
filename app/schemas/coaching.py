from pydantic import Field, field_validator
from app.schemas.domain import ActivitySummary, DomainModel, ProfileOut
from app.schemas.history import HistoryItem, SessionDetail
from app.schemas.reviews import DraftOut


class RosterQuery(DomainModel):
    limit: int = Field(default=20, ge=1, le=100)
    cursor: str | None = None
    q: str = Field(default="", max_length=120)

    @field_validator("q", mode="before")
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value


class RosterMember(DomainModel):
    profile: ProfileOut
    latestSession: HistoryItem | None


class RosterDetail(RosterMember):
    statistics: ActivitySummary


class RosterPage(DomainModel):
    items: list[RosterMember]
    nextCursor: str | None


class CoachSessionDetail(SessionDetail):
    feedbackDraft: DraftOut | None


class IssueCount(DomainModel):
    feature: str
    sessionCount: int


class CoachOverview(DomainModel):
    memberCount: int
    reviewQueueCount: int
    statistics: ActivitySummary
    recentSessions: list[HistoryItem]
    topIssues: list[IssueCount]
