from datetime import datetime, timezone
from sqlalchemy import (
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    Float,
    JSON,
    UniqueConstraint,
    Index,
    BigInteger,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.mysql import DATETIME
from app.db.session import Base


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(254), unique=True, index=True)
    npm: Mapped[str | None] = mapped_column(String(12), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(10), default="MEMBER")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    auth_version: Mapped[int] = mapped_column(default=0, server_default="0")
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime)


class MemberProfile(Base):
    __tablename__ = "member_profiles"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    division: Mapped[str | None] = mapped_column(String(120))
    belt: Mapped[str | None] = mapped_column(String(120))
    belt_target: Mapped[str | None] = mapped_column(String(120))


class CoachProfile(Base):
    __tablename__ = "coach_profiles"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    division: Mapped[str | None] = mapped_column(String(120))
    title: Mapped[str | None] = mapped_column(String(120))


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    persistent: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    auth_version: Mapped[int] = mapped_column(default=0, server_default="0")


class RecoveryToken(Base):
    __tablename__ = "recovery_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    purpose: Mapped[str] = mapped_column(String(16))
    email: Mapped[str] = mapped_column(String(254))
    auth_version: Mapped[int] = mapped_column()
    expires_at: Mapped[datetime] = mapped_column(DateTime().with_variant(DATETIME(fsp=6), "mysql"), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime().with_variant(DATETIME(fsp=6), "mysql"))


class AuthRateBucket(Base):
    __tablename__ = "auth_rate_buckets"
    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    count: Mapped[int] = mapped_column(default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime().with_variant(DATETIME(fsp=6), "mysql"), index=True)


class Movement(Base):
    __tablename__ = "movements"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    display_order: Mapped[int] = mapped_column(default=0, server_default="0")
    description: Mapped[str | None] = mapped_column(Text)
    level: Mapped[str | None] = mapped_column(String(120))
    estimated_duration_seconds: Mapped[int | None] = mapped_column()
    checklist: Mapped[list | None] = mapped_column(JSON)
    guides: Mapped[list | None] = mapped_column(JSON)


class ReferenceProfile(Base):
    __tablename__ = "reference_profiles"
    __table_args__ = (UniqueConstraint("movement", "variant", "version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    movement: Mapped[str] = mapped_column(String(40))
    variant: Mapped[str] = mapped_column(String(80))
    version: Mapped[str] = mapped_column(String(120))
    artifact_path: Mapped[str] = mapped_column(String(500))
    evaluator_type: Mapped[str] = mapped_column(String(80))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class EvaluationSession(Base):
    __tablename__ = "evaluation_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    training_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("training_sessions.id"), unique=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    movement: Mapped[str] = mapped_column(String(40))
    matched_variant: Mapped[str | None] = mapped_column(String(80), nullable=True)
    reference_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("reference_profiles.id"), nullable=True
    )
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(40))
    analyzer_version: Mapped[str] = mapped_column(String(80))
    reference_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    result_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    issues: Mapped[list["EvaluationIssue"]] = relationship(cascade="all, delete-orphan")
    notes: Mapped[list["CoachNote"]] = relationship(
        cascade="all, delete-orphan", order_by="CoachNote.created_at"
    )


class EvaluationIssue(Base):
    __tablename__ = "evaluation_issues"
    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_sessions.id"), index=True
    )
    body_part: Mapped[str] = mapped_column(String(80))
    feature: Mapped[str] = mapped_column(String(100))
    deviation: Mapped[float] = mapped_column(Float)
    severity: Mapped[str] = mapped_column(String(20))
    feedback: Mapped[str] = mapped_column(Text)


class CoachNote(Base):
    __tablename__ = "coach_notes"
    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_sessions.id"), index=True
    )
    coach_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    coach: Mapped[User] = relationship()


class TrainingSession(Base):
    __tablename__ = "training_sessions"
    __table_args__ = (
        Index("ix_training_owner_status", "user_id", "processing_status"),
        Index("ix_training_owner_history", "user_id", "deleted_at", "created_at", "id"),
        Index("ix_training_owner_completed", "user_id", "deleted_at", "processing_status", "completed_at", "id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    movement: Mapped[str] = mapped_column(String(40))
    processing_status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime().with_variant(DATETIME(fsp=6), "mysql"), default=now)
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime().with_variant(DATETIME(fsp=6), "mysql"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime().with_variant(DATETIME(fsp=6), "mysql"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime().with_variant(DATETIME(fsp=6), "mysql"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime().with_variant(DATETIME(fsp=6), "mysql"))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime().with_variant(DATETIME(fsp=6), "mysql"))
    retry_of: Mapped[int | None] = mapped_column(ForeignKey("training_sessions.id"))
    error_code: Mapped[str | None] = mapped_column(String(64))


class MediaAsset(Base):
    __tablename__ = "media_assets"
    __table_args__ = (Index("ix_media_expiry", "expires_at", "deleted_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("training_sessions.id"), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    storage_key: Mapped[str] = mapped_column(String(100), unique=True)
    mime_type: Mapped[str] = mapped_column(String(80))
    byte_size: Mapped[int] = mapped_column(BigInteger)
    checksum: Mapped[str] = mapped_column(String(64))
    duration_seconds: Mapped[float] = mapped_column(Float)
    width: Mapped[int] = mapped_column()
    height: Mapped[int] = mapped_column()
    expires_at: Mapped[datetime] = mapped_column(DateTime().with_variant(DATETIME(fsp=6), "mysql"))
    deletion_requested_at: Mapped[datetime | None] = mapped_column(DateTime().with_variant(DATETIME(fsp=6), "mysql"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime().with_variant(DATETIME(fsp=6), "mysql"))


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"
    __table_args__ = (
        Index("ix_analysis_jobs_ready", "state", "available_at"),
        Index("ix_analysis_jobs_lease", "state", "lease_until"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("training_sessions.id"), unique=True)
    state: Mapped[str] = mapped_column(String(16))
    attempt: Mapped[int] = mapped_column(default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime().with_variant(DATETIME(fsp=6), "mysql"), default=now)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime().with_variant(DATETIME(fsp=6), "mysql"))
    claim_token: Mapped[str | None] = mapped_column(String(64))
    worker_id: Mapped[str | None] = mapped_column(String(120))
    reference_snapshot: Mapped[list] = mapped_column(JSON)
    processing_config: Mapped[dict] = mapped_column(JSON)
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime().with_variant(DATETIME(fsp=6), "mysql"), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime().with_variant(DATETIME(fsp=6), "mysql"))


class UploadReservation(Base):
    __tablename__ = "upload_reservations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    storage_key: Mapped[str] = mapped_column(String(100), unique=True)
    reserved_bytes: Mapped[int] = mapped_column(BigInteger)
    expires_at: Mapped[datetime] = mapped_column(DateTime().with_variant(DATETIME(fsp=6), "mysql"), index=True)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("user_id", "operation", "key_hash", name="uq_idempotency_owner_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    operation: Mapped[str] = mapped_column(String(32))
    key_hash: Mapped[str] = mapped_column(String(64))
    fingerprint: Mapped[str] = mapped_column(String(64))
    session_id: Mapped[int] = mapped_column(ForeignKey("training_sessions.id"))
    response_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime().with_variant(DATETIME(fsp=6), "mysql"), default=now)


class AssignmentEvent(Base):
    __tablename__ = "assignment_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    from_coach_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    to_coach_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    actor: Mapped[str] = mapped_column(String(120))
    reason: Mapped[str] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(DateTime().with_variant(DATETIME(fsp=6), "mysql"), default=now)


class CoachAssignment(Base):
    __tablename__ = "coach_member_assignments"
    member_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    coach_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("assignment_events.id"), unique=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime().with_variant(DATETIME(fsp=6), "mysql"), default=now)


class FeedbackDraft(Base):
    __tablename__ = "feedback_drafts"
    __table_args__ = (UniqueConstraint("session_id", "assignment_event_id", name="uq_draft_session_assignment"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("training_sessions.id"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    assignment_event_id: Mapped[int] = mapped_column(ForeignKey("assignment_events.id"))
    version: Mapped[int] = mapped_column()
    payload: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime().with_variant(DATETIME(fsp=6), "mysql"), default=now)


class ReviewRevision(Base):
    __tablename__ = "review_revisions"
    __table_args__ = (UniqueConstraint("session_id", "revision", name="uq_review_session_revision"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("training_sessions.id"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    assignment_event_id: Mapped[int] = mapped_column(ForeignKey("assignment_events.id"))
    revision: Mapped[int] = mapped_column()
    decision: Mapped[str] = mapped_column(String(20))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime().with_variant(DATETIME(fsp=6), "mysql"), default=now, index=True)


class ReviewHead(Base):
    __tablename__ = "review_heads"
    session_id: Mapped[int] = mapped_column(ForeignKey("training_sessions.id"), primary_key=True)
    review_id: Mapped[int] = mapped_column(ForeignKey("review_revisions.id"), unique=True)


class FollowUpTask(Base):
    __tablename__ = "follow_up_tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("training_sessions.id"), index=True)
    review_id: Mapped[int] = mapped_column(ForeignKey("review_revisions.id"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    instruction: Mapped[str] = mapped_column(String(2000))
    status: Mapped[str] = mapped_column(String(12), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime().with_variant(DATETIME(fsp=6), "mysql"), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime().with_variant(DATETIME(fsp=6), "mysql"), default=now)


class RetryIntent(Base):
    __tablename__ = "retry_intents"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    source_session_id: Mapped[int] = mapped_column(ForeignKey("training_sessions.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime().with_variant(DATETIME(fsp=6), "mysql"), default=now)


from sqlalchemy import event


@event.listens_for(ReviewRevision, "before_update")
@event.listens_for(ReviewRevision, "before_delete")
@event.listens_for(AssignmentEvent, "before_update")
@event.listens_for(AssignmentEvent, "before_delete")
def immutable_history(mapper, connection, target):
    raise ValueError("Published reviews and assignment events are immutable")
