"""short-term conversation context buffer

Revision ID: i8d9e0f1a2b3
Revises: h7c8d9e0f1a2
Create Date: 2026-05-05 12:00:00.000000

Per-user rolling buffer of recent (user, assistant) message pairs. Read
by the agent layer to inject conversation history into LLM prompts so
follow-ups like "so với tháng 3 thì sao?" resolve against the prior
turn. Append-only; pruning happens on read (TTL filter) plus a
periodic cleanup outside this migration.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "i8d9e0f1a2b3"
down_revision: Union[str, Sequence[str], None] = "h7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversation_context",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"), nullable=False,
        ),
        # 'user' or 'assistant'. Kept as a string (not enum) so future
        # roles (e.g. 'system_note') don't need a migration.
        sa.Column("role", sa.String(20), nullable=False),
        # Truncated content — see service for the cap. Text type so we
        # don't need to migrate again if the cap loosens.
        sa.Column("content", sa.Text(), nullable=False),
        # Optional intent label captured at the time the row was written.
        # Useful for analytics and for prompts that want a hint about
        # what kind of turn the previous one was.
        sa.Column("intent", sa.String(50), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"), nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # The only query shape: latest N rows for a given user, newest first.
    op.create_index(
        "idx_conv_ctx_user_time",
        "conversation_context",
        ["user_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("idx_conv_ctx_user_time", table_name="conversation_context")
    op.drop_table("conversation_context")
