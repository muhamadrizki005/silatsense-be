"""Initial prototype schema.

Revision ID: 0001
"""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("expires_at", sa.DateTime, nullable=False),
        sa.Column("revoked", sa.Boolean, nullable=False),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_table(
        "movements",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("slug", sa.String(40), unique=True, nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False),
    )
    op.create_table(
        "reference_profiles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("movement", sa.String(40), nullable=False),
        sa.Column("variant", sa.String(80), nullable=False),
        sa.Column("version", sa.String(120), nullable=False),
        sa.Column("artifact_path", sa.String(500), nullable=False),
        sa.Column("evaluator_type", sa.String(80), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("movement", "variant", "version"),
    )
    op.create_table(
        "evaluation_sessions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("movement", sa.String(40), nullable=False),
        sa.Column("matched_variant", sa.String(80)),
        sa.Column(
            "reference_profile_id", sa.Integer, sa.ForeignKey("reference_profiles.id")
        ),
        sa.Column("score", sa.Float),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("analyzer_version", sa.String(80), nullable=False),
        sa.Column("reference_version", sa.String(120)),
        sa.Column("result_json", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index(
        "ix_evaluation_sessions_user_id", "evaluation_sessions", ["user_id"]
    )
    op.create_index(
        "ix_evaluation_sessions_created_at", "evaluation_sessions", ["created_at"]
    )
    op.create_table(
        "evaluation_issues",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "evaluation_id",
            sa.Integer,
            sa.ForeignKey("evaluation_sessions.id"),
            nullable=False,
        ),
        sa.Column("body_part", sa.String(80), nullable=False),
        sa.Column("feature", sa.String(100), nullable=False),
        sa.Column("deviation", sa.Float, nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("feedback", sa.Text, nullable=False),
    )
    op.create_index(
        "ix_evaluation_issues_evaluation_id", "evaluation_issues", ["evaluation_id"]
    )
    op.create_table(
        "coach_notes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "evaluation_id",
            sa.Integer,
            sa.ForeignKey("evaluation_sessions.id"),
            nullable=False,
        ),
        sa.Column("coach_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("note", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_coach_notes_evaluation_id", "coach_notes", ["evaluation_id"])


def downgrade():
    for table in [
        "coach_notes",
        "evaluation_issues",
        "evaluation_sessions",
        "reference_profiles",
        "movements",
        "refresh_tokens",
        "users",
    ]:
        op.drop_table(table)
