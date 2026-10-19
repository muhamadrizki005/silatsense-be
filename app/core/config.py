from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, model_validator
from typing import Literal


class Settings(BaseSettings):
    database_url: str = (
        "mysql+pymysql://silatsense:local-prototype-password@localhost:3306/silatsense"
    )
    jwt_secret: str = "local-only-change-this-secret-before-sharing"
    frontend_origin: str = "http://localhost:3000"
    cookie_secure: bool = False
    mail_adapter: Literal["disabled", "smtp"] = "disabled"
    smtp_host: str = "localhost"
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_from: str = "noreply@localhost"
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_starttls: bool = True
    smtp_timeout_seconds: float = Field(default=10, gt=0, le=30)
    auth_attempts_per_15_minutes: int = Field(default=10, ge=1)
    auth_ip_requests_per_15_minutes: int = Field(default=120, ge=1)
    signup_ip_requests_per_hour: int = Field(default=20, ge=1)
    pose_model_path: str = "artifacts/pose/pose_landmarker_lite.task"
    reference_root: str = "artifacts/reference_profiles"
    sample_fps: float = 2
    max_video_mb: int = 100
    max_video_seconds: int = 60
    media_root: str = ".data/media"
    media_retention_hours: int = Field(default=24, ge=24, le=24)
    upload_quota_mb: int = Field(default=500, ge=1)
    max_pending_sessions: int = Field(default=2, ge=1)
    upload_reservation_seconds: int = Field(default=300, ge=60)
    video_probe_timeout_seconds: float = Field(default=30, gt=0)
    max_video_dimension: int = Field(default=3840, ge=1)
    max_video_short_dimension: int = Field(default=2160, ge=1)
    process_memory_mb: int = Field(default=2048, ge=128)
    worker_concurrency: int = Field(default=1, ge=1, le=8)
    worker_poll_seconds: float = Field(default=1, gt=0)
    worker_lease_seconds: int = Field(default=60, ge=3)
    worker_heartbeat_seconds: float = Field(default=15, gt=0)
    worker_job_timeout_seconds: float = Field(default=120, gt=0)
    worker_max_attempts: int = Field(default=3, ge=1)
    cleanup_interval_seconds: float = Field(default=60, gt=0)
    cleanup_batch_size: int = Field(default=100, ge=1, le=1000)
    orphan_grace_seconds: int = Field(default=3600, ge=300)
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def heartbeat_before_lease(self):
        if self.worker_heartbeat_seconds >= self.worker_lease_seconds:
            raise ValueError("Worker heartbeat must be shorter than its lease")
        return self


settings = Settings()
