"""Internal analyzer payload validation, separate from public camelCase DTOs."""

from typing import Literal

from pydantic import BaseModel


class AnalysisSummary(BaseModel):
    frames_processed: int
    valid_pose_frames: int
    key_frame: int | None
    key_frame_time: float | None = None
    method: str = "static-reference-pose"
    features_compared: int | None = None


class AnalysisIssue(BaseModel):
    body_part: str
    feature: str
    deviation: float
    severity: Literal["low", "medium", "high"]
    feedback: str


class AnalysisModel(BaseModel):
    analyzer_version: str
    reference_version: str | None
