"""Phase 4.2.5 analytics feature events

Revision ID: 20260515p425events
Revises: 20260514p425admin
Create Date: 2026-05-15 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260515p425events"
down_revision: Union[str, Sequence[str], None] = "20260514p425admin"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "feature_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("feature_key", sa.String(length=100), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_feature_events_user", "feature_events", ["user_id"])
    op.create_index("idx_feature_events_feature", "feature_events", ["feature_key", "created_at"])
    op.create_index("idx_feature_events_created", "feature_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_feature_events_created", table_name="feature_events")
    op.drop_index("idx_feature_events_feature", table_name="feature_events")
    op.drop_index("idx_feature_events_user", table_name="feature_events")
    op.drop_table("feature_events")
