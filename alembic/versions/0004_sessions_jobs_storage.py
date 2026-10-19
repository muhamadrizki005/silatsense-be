"""Persistent uploads, fenced jobs and legacy result linkage.

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import DATETIME

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None
timestamp = sa.DateTime().with_variant(DATETIME(fsp=6), "mysql")


def upgrade():
    op.create_table("training_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("movement", sa.String(40), nullable=False),
        sa.Column("processing_status", sa.String(16), nullable=False),
        sa.Column("created_at", timestamp, nullable=False),
        *[sa.Column(name, timestamp, nullable=True) for name in
          ["uploaded_at", "started_at", "completed_at", "deleted_at", "acknowledged_at"]],
        sa.Column("retry_of", sa.Integer(), sa.ForeignKey("training_sessions.id"), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
    )
    op.create_index("ix_training_owner_status", "training_sessions", ["user_id", "processing_status"])
    # This table is new: legacy evaluation IDs can safely initialize session IDs.
    op.execute(sa.text("""INSERT INTO training_sessions
        (id,user_id,movement,processing_status,created_at,completed_at)
        SELECT id,user_id,movement,'completed',created_at,created_at FROM evaluation_sessions"""))
    with op.batch_alter_table("evaluation_sessions") as batch:
        batch.add_column(sa.Column("training_session_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_evaluation_training_session", "training_sessions", ["training_session_id"], ["id"])
        batch.create_unique_constraint("uq_evaluation_training_session", ["training_session_id"])
    op.execute(sa.text("UPDATE evaluation_sessions SET training_session_id=id"))
    op.create_table("media_assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("training_sessions.id"), unique=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("storage_key", sa.String(100), unique=True, nullable=False),
        sa.Column("mime_type", sa.String(80), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("expires_at", timestamp, nullable=False),
        sa.Column("deletion_requested_at", timestamp, nullable=True),
        sa.Column("deleted_at", timestamp, nullable=True),
    )
    op.create_index("ix_media_assets_user_id", "media_assets", ["user_id"])
    op.create_index("ix_media_expiry", "media_assets", ["expires_at", "deleted_at"])
    op.create_table("analysis_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("training_sessions.id"), unique=True, nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("available_at", timestamp, nullable=False),
        sa.Column("lease_until", timestamp, nullable=True),
        sa.Column("claim_token", sa.String(64), nullable=True),
        sa.Column("worker_id", sa.String(120), nullable=True),
        sa.Column("reference_snapshot", sa.JSON(), nullable=False),
        sa.Column("processing_config", sa.JSON(), nullable=False),
        sa.Column("last_error_code", sa.String(64), nullable=True),
        sa.Column("created_at", timestamp, nullable=False),
        sa.Column("finished_at", timestamp, nullable=True),
    )
    op.create_index("ix_analysis_jobs_ready", "analysis_jobs", ["state", "available_at"])
    op.create_index("ix_analysis_jobs_lease", "analysis_jobs", ["state", "lease_until"])
    op.create_table("upload_reservations",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("storage_key", sa.String(100), unique=True, nullable=False),
        sa.Column("reserved_bytes", sa.BigInteger(), nullable=False),
        sa.Column("expires_at", timestamp, nullable=False),
    )
    op.create_index("ix_upload_reservations_user_id", "upload_reservations", ["user_id"])
    op.create_index("ix_upload_reservations_expires_at", "upload_reservations", ["expires_at"])
    op.create_table("idempotency_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("operation", sa.String(32), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("training_sessions.id"), nullable=False),
        sa.Column("response_json", sa.JSON(), nullable=False),
        sa.Column("created_at", timestamp, nullable=False),
        sa.UniqueConstraint("user_id", "operation", "key_hash", name="uq_idempotency_owner_key"),
    )


def downgrade():
    for name in ["idempotency_records", "upload_reservations", "analysis_jobs", "media_assets"]:
        op.drop_table(name)
    with op.batch_alter_table("evaluation_sessions") as batch:
        batch.drop_constraint("fk_evaluation_training_session", type_="foreignkey")
        batch.drop_constraint("uq_evaluation_training_session", type_="unique")
        batch.drop_column("training_session_id")
    op.drop_table("training_sessions")
