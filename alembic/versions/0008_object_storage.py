"""Direct uploads and metadata deferred until worker validation; preserve existing rows."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import DATETIME

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "direct_uploads",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("request_json", sa.JSON(), nullable=False),
        sa.Column(
            "expires_at",
            sa.DateTime().with_variant(DATETIME(fsp=6), "mysql"),
            nullable=False,
        ),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("training_sessions.id")),
        sa.Column("response_json", sa.JSON(), nullable=True),
        sa.UniqueConstraint("user_id", "key_hash", name="uq_direct_upload_owner_key"),
    )
    op.create_index("ix_direct_uploads_user_id", "direct_uploads", ["user_id"])
    with op.batch_alter_table("media_assets") as batch:
        batch.alter_column("duration_seconds", existing_type=sa.Float(), nullable=True)
        batch.alter_column("width", existing_type=sa.Integer(), nullable=True)
        batch.alter_column("height", existing_type=sa.Integer(), nullable=True)


def downgrade():
    # Never replace unavailable metadata with dummy zeroes during downgrade.
    connection = op.get_bind()
    pending = connection.scalar(
        sa.text(
            "SELECT COUNT(*) FROM media_assets WHERE duration_seconds IS NULL OR width IS NULL OR height IS NULL"
        )
    )
    if pending:
        raise RuntimeError("Validate or remove pending remote media before downgrade")
    with op.batch_alter_table("media_assets") as batch:
        batch.alter_column("duration_seconds", existing_type=sa.Float(), nullable=False)
        batch.alter_column("width", existing_type=sa.Integer(), nullable=False)
        batch.alter_column("height", existing_type=sa.Integer(), nullable=False)
    op.drop_table("direct_uploads")
