"""Indexes for visible history and completed dashboard queries.

Revision ID: 0005
Revises: 0004
"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_training_owner_history", "training_sessions", ["user_id", "deleted_at", "created_at", "id"])
    op.create_index("ix_training_owner_completed", "training_sessions",
                    ["user_id", "deleted_at", "processing_status", "completed_at", "id"])


def downgrade():
    op.drop_index("ix_training_owner_completed", table_name="training_sessions")
    op.drop_index("ix_training_owner_history", table_name="training_sessions")
