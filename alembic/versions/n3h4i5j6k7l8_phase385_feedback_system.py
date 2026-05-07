"""phase 3.8.5 epic 1 — feedback system

Revision ID: n3h4i5j6k7l8
Revises: m2g3h4i5j6k7
Create Date: 2026-05-07 09:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "n3h4i5j6k7l8"
down_revision: Union[str, Sequence[str], None] = "m2g3h4i5j6k7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "feedbacks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("sentiment", sa.String(20), nullable=True),
        sa.Column("priority", sa.String(20), nullable=True),
        sa.Column("classification_confidence", sa.Float(), nullable=True),
        sa.Column("classifier_version", sa.String(50), nullable=True),
        sa.Column("classification_attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("classification_error", sa.Text(), nullable=True),
        sa.Column("trigger", sa.String(80), nullable=False, server_default=sa.text("'passive_command'")),
        sa.Column("context", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'new'")),
        sa.Column("admin_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_feedbacks_user_id", "feedbacks", ["user_id"])
    op.create_index("ix_feedbacks_category", "feedbacks", ["category"])
    op.create_index("ix_feedbacks_sentiment", "feedbacks", ["sentiment"])
    op.create_index("ix_feedbacks_priority", "feedbacks", ["priority"])
    op.create_index("ix_feedbacks_trigger", "feedbacks", ["trigger"])
    op.create_index("ix_feedbacks_status", "feedbacks", ["status"])
    op.create_index("ix_feedbacks_created_at", "feedbacks", ["created_at"])
    op.create_index("idx_feedbacks_user_created_at", "feedbacks", ["user_id", "created_at"])
    op.create_index(
        "idx_feedbacks_unclassified",
        "feedbacks",
        ["created_at"],
        postgresql_where=sa.text("category IS NULL"),
    )

    op.create_table(
        "prompts_sent_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prompt_id", sa.String(80), nullable=False),
        sa.Column("trigger", sa.String(80), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'sent'")),
        sa.Column("context", postgresql.JSONB(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("skipped_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prompts_sent_log_user_id", "prompts_sent_log", ["user_id"])
    op.create_index("ix_prompts_sent_log_prompt_id", "prompts_sent_log", ["prompt_id"])
    op.create_index("ix_prompts_sent_log_trigger", "prompts_sent_log", ["trigger"])
    op.create_index("ix_prompts_sent_log_status", "prompts_sent_log", ["status"])
    op.create_index("ix_prompts_sent_log_sent_at", "prompts_sent_log", ["sent_at"])
    op.create_index("idx_prompts_user_prompt_sent", "prompts_sent_log", ["user_id", "prompt_id", "sent_at"])
    op.create_index("idx_prompts_user_sent", "prompts_sent_log", ["user_id", "sent_at"])


def downgrade() -> None:
    op.drop_index("idx_prompts_user_sent", table_name="prompts_sent_log")
    op.drop_index("idx_prompts_user_prompt_sent", table_name="prompts_sent_log")
    op.drop_index("ix_prompts_sent_log_sent_at", table_name="prompts_sent_log")
    op.drop_index("ix_prompts_sent_log_status", table_name="prompts_sent_log")
    op.drop_index("ix_prompts_sent_log_trigger", table_name="prompts_sent_log")
    op.drop_index("ix_prompts_sent_log_prompt_id", table_name="prompts_sent_log")
    op.drop_index("ix_prompts_sent_log_user_id", table_name="prompts_sent_log")
    op.drop_table("prompts_sent_log")

    op.drop_index("idx_feedbacks_unclassified", table_name="feedbacks")
    op.drop_index("idx_feedbacks_user_created_at", table_name="feedbacks")
    op.drop_index("ix_feedbacks_created_at", table_name="feedbacks")
    op.drop_index("ix_feedbacks_status", table_name="feedbacks")
    op.drop_index("ix_feedbacks_trigger", table_name="feedbacks")
    op.drop_index("ix_feedbacks_priority", table_name="feedbacks")
    op.drop_index("ix_feedbacks_sentiment", table_name="feedbacks")
    op.drop_index("ix_feedbacks_category", table_name="feedbacks")
    op.drop_index("ix_feedbacks_user_id", table_name="feedbacks")
    op.drop_table("feedbacks")
