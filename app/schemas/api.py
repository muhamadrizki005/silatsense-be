from typing import Literal
from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def email_lower(cls, value):
        return value.lower()


class Register(Credentials):
    name: str = Field(min_length=2, max_length=120)
    model_config = ConfigDict(extra="forbid")

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        if len(value.strip()) < 2:
            raise ValueError("Nama minimal 2 karakter")
        return value.strip()


class UserOut(BaseModel):
    id: int
    name: str
    email: str | None
    role: Literal["MEMBER", "COACH"]
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ProfilePatch(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    model_config = ConfigDict(extra="forbid")

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        if len(value.strip()) < 2:
            raise ValueError("Nama minimal 2 karakter")
        return value.strip()


class NoteCreate(BaseModel):
    note: str = Field(min_length=1, max_length=5000)

    @field_validator("note")
    @classmethod
    def clean_note(cls, value):
        if not value.strip():
            raise ValueError("Catatan tidak boleh kosong")
        return value.strip()


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"]
    user: UserOut


class MovementOut(BaseModel):
    slug: str
    name: str
    reference_ready: bool


class AnalysisOut(BaseModel):
    frames_processed: int
    valid_pose_frames: int
    key_frame: int | None
    key_frame_time: float | None = None
    method: str = "static-reference-pose"
    features_compared: int | None = None


class IssueOut(BaseModel):
    body_part: str
    feature: str
    deviation: float
    severity: Literal["low", "medium", "high"]
    feedback: str


class ModelOut(BaseModel):
    analyzer_version: str
    reference_version: str | None


class NoteOut(BaseModel):
    id: int
    coach_name: str
    note: str
    created_at: str


class EvaluationOut(BaseModel):
    id: int
    movement: str
    matched_variant: str | None
    reference_profile_id: int | None
    score: float | None
    status: Literal[
        "experimental",
        "reference_not_ready",
        "insufficient_pose",
        "insufficient_features",
    ]
    pose_status: Literal["detected", "not_detected"]
    analysis: AnalysisOut
    issues: list[IssueOut]
    model: ModelOut
    created_at: str
    coach_notes: list[NoteOut]
