"""Current assignments, immutable review revisions and follow-ups.
Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import DATETIME

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None
stamp = sa.DateTime().with_variant(DATETIME(fsp=6), "mysql")


def fk(name, target, nullable=False, **kwargs):
    return sa.Column(name, sa.Integer(), sa.ForeignKey(target), nullable=nullable, **kwargs)


def upgrade():
    op.create_table("assignment_events", sa.Column("id", sa.Integer(), primary_key=True),
        fk("member_id", "users.id"), fk("from_coach_id", "users.id", True), fk("to_coach_id", "users.id", True),
        sa.Column("actor", sa.String(120), nullable=False), sa.Column("reason", sa.String(2000), nullable=False),
        sa.Column("created_at", stamp, nullable=False))
    op.create_index("ix_assignment_events_member_id", "assignment_events", ["member_id"])
    op.create_table("coach_member_assignments", fk("member_id", "users.id", primary_key=True),
        fk("coach_id", "users.id"), fk("event_id", "assignment_events.id", unique=True),
        sa.Column("assigned_at", stamp, nullable=False))
    op.create_index("ix_coach_member_assignments_coach_id", "coach_member_assignments", ["coach_id"])
    op.create_table("feedback_drafts", sa.Column("id", sa.Integer(), primary_key=True),
        fk("session_id", "training_sessions.id"), fk("author_id", "users.id"), fk("assignment_event_id", "assignment_events.id"),
        sa.Column("version", sa.Integer(), nullable=False), sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("updated_at", stamp, nullable=False),
        sa.UniqueConstraint("session_id", "assignment_event_id", name="uq_draft_session_assignment"))
    op.create_index("ix_feedback_drafts_session_id", "feedback_drafts", ["session_id"])
    op.create_table("review_revisions", sa.Column("id", sa.Integer(), primary_key=True),
        fk("session_id", "training_sessions.id"), fk("author_id", "users.id"), fk("assignment_event_id", "assignment_events.id"),
        sa.Column("revision", sa.Integer(), nullable=False), sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False), sa.Column("created_at", stamp, nullable=False),
        sa.UniqueConstraint("session_id", "revision", name="uq_review_session_revision"))
    op.create_index("ix_review_revisions_session_id", "review_revisions", ["session_id"])
    op.create_index("ix_review_revisions_created_at", "review_revisions", ["created_at"])
    op.create_table("review_heads", fk("session_id", "training_sessions.id", primary_key=True),
        fk("review_id", "review_revisions.id", unique=True))
    op.create_table("follow_up_tasks", sa.Column("id", sa.Integer(), primary_key=True),
        fk("session_id", "training_sessions.id"), fk("review_id", "review_revisions.id"), fk("author_id", "users.id"),
        sa.Column("instruction", sa.String(2000), nullable=False), sa.Column("status", sa.String(12), nullable=False),
        sa.Column("created_at", stamp, nullable=False), sa.Column("updated_at", stamp, nullable=False))
    op.create_index("ix_follow_up_tasks_session_id", "follow_up_tasks", ["session_id"])
    op.create_index("ix_follow_up_tasks_review_id", "follow_up_tasks", ["review_id"])
    op.create_table("retry_intents", sa.Column("id", sa.Integer(), primary_key=True),
        fk("user_id", "users.id"), fk("source_session_id", "training_sessions.id"), sa.Column("created_at", stamp, nullable=False))
    op.create_index("ix_retry_intents_source_session_id", "retry_intents", ["source_session_id"])


def downgrade():
    for table in ("retry_intents", "follow_up_tasks", "review_heads", "review_revisions",
                  "feedback_drafts", "coach_member_assignments", "assignment_events"):
        op.drop_table(table)
