"""Additive, public reference-comparison DTOs; never a correctness verdict."""

from typing import Literal

from pydantic import ConfigDict, Field

from app.schemas.domain import DomainModel
from app.intelligence.coach_contracts import MovementId


class FiniteModel(DomainModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class FeatureComparison(FiniteModel):
    value: float | None
    referenceValue: float | None
    deviation: float | None = Field(ge=0)
    unit: Literal["deg", "torso_length_ratio"]
    color: Literal["green", "yellow", "red"] | None
    reason: str | None


class JointComparison(FeatureComparison):
    landmarkIndices: list[int] = Field(min_length=3, max_length=3)
    feedbackCode: str | None


class ComparisonFrame(FiniteModel):
    timeSeconds: float = Field(ge=0)
    referenceTimeSeconds: float = Field(ge=0)
    phase: str | None
    features: dict[str, FeatureComparison]
    joints: dict[str, JointComparison]


class FeatureSummary(FiniteModel):
    sampleCount: int = Field(ge=0, le=32)
    coverage: float = Field(ge=0, le=1)
    medianDeviation: float | None = Field(ge=0)
    maximumDeviation: float | None = Field(ge=0)
    unit: Literal["deg", "torso_length_ratio"]
    colorCounts: dict[str, int]


class PostureAspect(FiniteModel):
    id: str
    points: int | None = Field(ge=0, le=100)
    correctionCode: str | None
    reason: str | None
    unit: Literal["deg", "torso_length_ratio"]


class PostureAssessment(FiniteModel):
    """Experimental reference points; separate from similarity/manual Coach scores."""

    status: Literal["assessed", "partial", "not_assessable"]
    points: float | None = Field(ge=0, le=100)
    maxPoints: Literal[100] = 100
    reason: str | None
    aspects: list[PostureAspect]
    rubricVersion: Literal["posture-reference-v1"] = "posture-reference-v1"


class CoachComparison(FiniteModel):
    movementId: MovementId
    status: Literal["compared", "not_assessable"]
    reason: str | None = None
    experimental: Literal[True] = True
    correctness: None = None
    score: None = None
    qualityAssessmentValidated: Literal[False] = False
    toleranceStatus: str
    alignmentDistance: float | None = Field(default=None, ge=0)
    semanticPhasesAvailable: bool = False
    frames: list[ComparisonFrame] = Field(max_length=32)
    features: dict[str, FeatureSummary]
    postureAssessment: PostureAssessment | None = Field(
        default=None,
        description="Computed on evaluation read from stored paired frames. Experimental equal-weight points, not an official correctness verdict or manual Coach assessment.",
    )


class TimelineLandmark(FiniteModel):
    index: int = Field(ge=0, le=32)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    visibility: float = Field(ge=0, le=1)


class TimelineFrame(FiniteModel):
    frameIndex: int = Field(ge=0)
    timeSeconds: float = Field(ge=0)
    landmarks: list[TimelineLandmark] = Field(min_length=1, max_length=33)


class PoseTimeline(FiniteModel):
    coordinateSystem: Literal["image-normalized"] = "image-normalized"
    origin: Literal["top-left"] = "top-left"
    imageWidth: int = Field(gt=0)
    imageHeight: int = Field(gt=0)
    maximumInterpolationGapSeconds: float = 0.15
    frames: list[TimelineFrame] = Field(max_length=900)
