"""Support NPM accounts and refresh cookie persistence.

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch:
        batch.alter_column("email", existing_type=sa.String(254), nullable=True)
        batch.add_column(sa.Column("npm", sa.String(12), nullable=True))
        batch.create_index("ix_users_npm", ["npm"], unique=True)
    op.add_column("refresh_tokens", sa.Column(
        "persistent", sa.Boolean(), nullable=False, server_default=sa.true(),
    ))


def downgrade():
    # NPM-only users must be assigned real email addresses before downgrading.
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT COUNT(*) FROM users WHERE email IS NULL")):
        raise RuntimeError("Assign email addresses to NPM accounts before downgrade")
    op.drop_column("refresh_tokens", "persistent")
    with op.batch_alter_table("users") as batch:
        batch.drop_index("ix_users_npm")
        batch.drop_column("npm")
        batch.alter_column("email", existing_type=sa.String(254), nullable=False)
