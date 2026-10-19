"""Profiles, catalog metadata and revocable account sessions.

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("auth_version", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("password_changed_at", sa.DateTime(), nullable=True))
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(), nullable=True))
    op.add_column("refresh_tokens", sa.Column("auth_version", sa.Integer(), nullable=False, server_default="0"))
    op.create_table(
        "member_profiles",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("division", sa.String(120), nullable=True),
        sa.Column("belt", sa.String(120), nullable=True),
        sa.Column("belt_target", sa.String(120), nullable=True),
    )
    op.create_table(
        "coach_profiles",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("division", sa.String(120), nullable=True),
        sa.Column("title", sa.String(120), nullable=True),
    )
    op.add_column("movements", sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"))
    for column in [
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("level", sa.String(120), nullable=True),
        sa.Column("estimated_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("checklist", sa.JSON(), nullable=True),
        sa.Column("guides", sa.JSON(), nullable=True),
    ]:
        op.add_column("movements", column)
    movement = sa.table("movements", sa.column("slug"), sa.column("display_order"))
    for order, slug in enumerate(["kuda_kuda", "pukulan", "tangkisan", "tendangan"], 1):
        op.execute(movement.update().where(movement.c.slug == slug).values(display_order=order))


def downgrade():
    for column in ["guides", "checklist", "estimated_duration_seconds", "level", "description", "display_order"]:
        op.drop_column("movements", column)
    op.drop_table("coach_profiles")
    op.drop_table("member_profiles")
    op.drop_column("refresh_tokens", "auth_version")
    for column in ["email_verified_at", "password_changed_at", "auth_version"]:
        op.drop_column("users", column)
