from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator
from app.schemas.domain import CoachIdentity, DomainModel
from app.schemas.sessions import SessionModel


class BodyAssessment(DomainModel):
    bodyPart: str = Field(min_length=1, max_length=80)
    status: Literal["not_assessed", "needs_revision", "approved"]
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("bodyPart", "note", mode="before")
    @classmethod
    def trim(cls, value, info):
        if isinstance(value, str):
            return (value.strip() or None) if info.field_name == "note" else value.strip()
        return value


class TaskInput(DomainModel):
    instruction: str = Field(min_length=1, max_length=2000)

    @field_validator("instruction", mode="before")
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value


class DraftInput(DomainModel):
    expectedVersion: int = Field(ge=0)
    decision: Literal["approved", "needs_revision"] | None = None
    note: str | None = Field(default=None, max_length=5000)
    bodyAssessments: list[BodyAssessment] = Field(default_factory=list, max_length=33)
    tasks: list[TaskInput] = Field(default_factory=list, max_length=20)

    @field_validator("note", mode="before")
    @classmethod
    def trim(cls, value):
        return (value.strip() or None) if isinstance(value, str) else value

    @model_validator(mode="after")
    def unique_parts(self):
        if len({row.bodyPart for row in self.bodyAssessments}) != len(self.bodyAssessments):
            raise ValueError("bodyPart harus unik.")
        return self


class DraftOut(SessionModel):
    version: int
    author: CoachIdentity
    updatedAt: datetime
    decision: Literal["approved", "needs_revision"] | None
    note: str | None
    bodyAssessments: list[BodyAssessment]
    tasks: list[TaskInput]


class PublishInput(DomainModel):
    expectedRevision: int = Field(ge=0)
    expectedDraftVersion: int = Field(ge=1)


class PublishedReview(SessionModel):
    id: str
    revision: int
    author: CoachIdentity
    publishedAt: datetime
    decision: Literal["approved", "needs_revision"]
    note: str | None
    bodyAssessments: list[BodyAssessment]
    taskIds: list[str]
    supersedesReviewId: str | None


class TaskOut(SessionModel):
    id: str
    sessionId: str
    reviewId: str
    author: CoachIdentity
    instruction: str
    status: Literal["open", "completed", "dismissed"]
    createdAt: datetime
    updatedAt: datetime


class TaskPatch(DomainModel):
    status: Literal["completed", "dismissed"]


class RetryInput(DomainModel):
    intent: Literal["retry"]


class RetryOut(SessionModel):
    id: str
    sourceSessionId: str
    createdAt: datetime
