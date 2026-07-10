"""phase 4.5 tone dial + re-engagement bookkeeping

Two nullable ``users`` columns land together because they belong to the
same Epic (E4/E5) and both default to "unset means default behaviour":

1. ``tone_preference VARCHAR(10) NULL`` — the tone dial (E4 #4.2). NULL →
   the default gentle voice; ``"gentle"`` / ``"strict"`` when the user has
   chosen. Kept nullable (no server_default) so existing rows read as the
   default without a backfill, and so the /profile control can distinguish
   "never chosen" from an explicit choice.

2. ``reengagement_broadcast_at TIMESTAMPTZ NULL`` — the one-time
   re-engagement broadcast marker (E5 #5.2). NULL → never messaged; set to
   the send time once the dormant-cohort broadcast reaches the user, so the
   nudge fires at most once.

Revision ID: 20260710tone45
Revises: 20260608ccsoftdel
Create Date: 2026-07-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260710tone45"
down_revision = "20260608ccsoftdel"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("tone_preference", sa.String(length=10), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "reengagement_broadcast_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "reengagement_broadcast_at")
    op.drop_column("users", "tone_preference")
