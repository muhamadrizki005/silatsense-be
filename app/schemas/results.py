from typing import Literal

from pydantic import Field, ConfigDict

from app.schemas.sessions import SessionModel
from app.schemas.domain import DomainModel, MovementSlug
from datetime import datetime


class Landmark(DomainModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    index: int = Field(ge=0, le=32)
    x: float
    y: float
    z: float
    visibility: float = Field(ge=0, le=1)


class KeyFrame(DomainModel):
    index: int = Field(ge=0)
    timeSeconds: float = Field(ge=0, allow_inf_nan=False)


class PoseData(DomainModel):
    kind: Literal["keyframe"] = "keyframe"
    frameIndex: int = Field(ge=0)
    timeSeconds: float = Field(ge=0, allow_inf_nan=False)
    coordinateSystem: Literal["image-normalized"] = "image-normalized"
    origin: Literal["top-left"] = "top-left"
    imageWidth: int = Field(gt=0)
    imageHeight: int = Field(gt=0)
    landmarks: list[Landmark] = Field(min_length=1, max_length=33)


class PoseOut(DomainModel):
    sessionId: str
    pose: PoseData | None
    reason: str | None


class Measurement(DomainModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    feature: str
    bodyPart: str
    value: float | None
    unit: Literal["deg", "shoulder_width"]
    referenceMedian: float | None
    referenceIqr: float | None
    deviation: float | None
    assessment: Literal["within_reference", "deviates", "not_assessed"]
    reason: str | None


class AnalysisIssue(DomainModel):
    feature: str
    bodyPart: str
    deviation: float = Field(allow_inf_nan=False)
    unit: Literal["deg", "shoulder_width"]
    severity: Literal["low", "medium", "high"]
    feedback: str


class EvaluationOut(SessionModel):
    id: str
    sessionId: str
    movementSlug: MovementSlug
    evaluatedAt: datetime
    analysisStatus: Literal["experimental", "reference_not_ready", "insufficient_pose", "insufficient_features"]
    score: float | None = Field(ge=0, le=100, allow_inf_nan=False)
    scoreUnit: Literal["similarity_points"] = "similarity_points"
    scoreReason: str | None
    matchedVariant: str | None
    method: Literal["static-reference-pose"] = "static-reference-pose"
    analyzerVersion: str
    featureVersion: str | None
    referenceVersion: str | None
    poseStatus: Literal["detected", "not_detected"]
    framesProcessed: int
    validPoseFrames: int
    featuresCompared: int | None
    keyFrame: KeyFrame | None
    measurements: list[Measurement]
    issues: list[AnalysisIssue]
    validRepetitions: None = None
    deviatedRepetitions: None = None
    unavailableReasons: list[str]


class AcknowledgedOut(SessionModel):
    acknowledgedAt: datetime
