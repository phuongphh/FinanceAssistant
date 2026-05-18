"""phase4.3 epic2 twin storytelling

Revision ID: 20260518p43twinstory
Revises: 20260518p43twincomp
Create Date: 2026-05-18 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260518p43twinstory"
down_revision = "20260518p43twincomp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "twin_view_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("screen_id", sa.String(length=40), nullable=True),
        sa.Column("flow_mode", sa.String(length=20), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_twin_view_events_user_created",
        "twin_view_events",
        ["user_id", "created_at"],
    )
    op.create_index(
        "idx_twin_view_events_type_created",
        "twin_view_events",
        ["event_type", "created_at"],
    )
    op.create_index(
        "idx_twin_view_events_screen_created",
        "twin_view_events",
        ["screen_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_twin_view_events_screen_created", table_name="twin_view_events")
    op.drop_index("idx_twin_view_events_type_created", table_name="twin_view_events")
    op.drop_index("idx_twin_view_events_user_created", table_name="twin_view_events")
    op.drop_table("twin_view_events")
