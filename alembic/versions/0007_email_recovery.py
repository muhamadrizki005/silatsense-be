"""Hashed one-use email recovery tokens and shared rate buckets."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import DATETIME

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None
stamp = sa.DateTime().with_variant(DATETIME(fsp=6), "mysql")


def upgrade():
    op.create_table(
        "recovery_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("auth_version", sa.Integer(), nullable=False),
        sa.Column("expires_at", stamp, nullable=False),
        sa.Column("used_at", stamp),
    )
    op.create_index("ix_recovery_tokens_user_id", "recovery_tokens", ["user_id"])
    op.create_index("ix_recovery_tokens_expires_at", "recovery_tokens", ["expires_at"])
    op.create_table(
        "auth_rate_buckets",
        sa.Column("key_hash", sa.String(64), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("expires_at", stamp, nullable=False),
    )
    op.create_index(
        "ix_auth_rate_buckets_expires_at", "auth_rate_buckets", ["expires_at"]
    )


def downgrade():
    op.drop_table("auth_rate_buckets")
    op.drop_table("recovery_tokens")
