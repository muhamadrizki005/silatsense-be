from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class SimilarityGroup(DomainModel):
    movementSlug: str
    method: str
    analyzerVersion: str
    featureVersion: str
    referenceVersion: str
    averageScore: float | None
    sampleCount: int


class ActivitySummary(DomainModel):
    completedSessionCount: int
    totalDurationSeconds: float
    durationSampleCount: int
    scoredSessionCount: int
    excludedScoreCount: int
    similarityGroups: list[SimilarityGroup]


class CoachIdentity(DomainModel):
    id: str
    fullName: str
    title: str | None


class ProfileOut(DomainModel):
    id: str
    role: Literal["member", "coach"]
    fullName: str
    npm: str | None
    email: str | None
    emailVerifiedAt: datetime | None
    division: str | None
    title: str | None
    belt: str | None
    beltTarget: str | None
    passwordChangedAt: datetime | None
    coach: CoachIdentity | None
    createdAt: datetime
    statistics: ActivitySummary | None

    @field_serializer("emailVerifiedAt", "passwordChangedAt", "createdAt")
    def utc_timestamp(self, value):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


class MemberProfilePatch(DomainModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={
        "examples": [{"fullName": "Nama Member", "division": "UKM Silat"}]
    })
    fullName: str | None = Field(default=None, max_length=120)
    division: str | None = Field(default=None, max_length=120)

    @field_validator("fullName", "division")
    @classmethod
    def clean_text(cls, value, info):
        if value is None:
            return value
        value = value.strip()
        minimum = 3 if info.field_name == "fullName" else 1
        if len(value) < minimum:
            raise ValueError(f"Minimal {minimum} karakter.")
        return value

    @model_validator(mode="after")
    def meaningful_patch(self):
        if not self.model_fields_set:
            raise ValueError("Kirim minimal satu field.")
        if "fullName" in self.model_fields_set and self.fullName is None:
            raise ValueError("Nama tidak boleh null.")
        return self


class CoachProfilePatch(MemberProfilePatch):
    title: str | None = Field(default=None, max_length=120)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value):
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Judul tidak boleh kosong.")
        return value


class PasswordChange(DomainModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={
        "examples": [{"currentPassword": "<kata-sandi-lama>", "newPassword": "<kata-sandi-baru>"}]
    })
    currentPassword: str = Field(min_length=8, max_length=128)
    newPassword: str = Field(min_length=8, max_length=128)


MovementSlug = Literal["kuda-kuda", "pukulan", "tangkisan", "tendangan"]


class Capability(DomainModel):
    scoringAvailable: bool
    reason: Literal["reference_not_ready"] | None
    method: Literal["static-reference-pose"] = "static-reference-pose"
    referenceVersions: list[str]
    repetitionCountingAvailable: Literal[False] = False


class GuideItem(DomainModel):
    id: str
    text: Annotated[str, Field(min_length=1)]
    source: Annotated[str, Field(min_length=1)]


class TrainingModule(DomainModel):
    slug: MovementSlug
    name: str
    order: int
    description: str | None
    level: str | None
    estimatedDurationSeconds: int | None
    capability: Capability


class TrainingCatalog(DomainModel):
    modules: list[TrainingModule]
    statistics: ActivitySummary


class TrainingPrep(DomainModel):
    module: TrainingModule
    checklist: list[GuideItem]
    guides: list[GuideItem]


class UploadConfig(DomainModel):
    movementSlug: MovementSlug
    acceptedMimeTypes: list[str]
    maxBytes: int
    maxDurationSeconds: int
    retentionSeconds: Literal[86400] = 86400
    recommendedDurationSeconds: int | None


class ValidationIssue(DomainModel):
    field: str
    message: str


class DomainErrorOut(DomainModel):
    detail: str
    code: str
    requestId: str
    errors: list[ValidationIssue] | None = None
