"""phase4.3 segment-aware expense recompute trigger

Adds a per-segment recompute trigger amount to `twin_delta_threshold_config`
so the on-demand Twin recompute (Story 3.1) only fires for expenses that
matter at the user's wealth scale. The notification thresholds (1%/0.5% and
1tr-50tr absolute) stay unchanged — this column gates compute, not notify.

Seed values mirror the segment matrix shipped with the recompute design:
  starter        →   100,000 VND
  young_pro      →   500,000 VND
  mass_affluent  → 2,000,000 VND
  hnw            → 10,000,000 VND

Revision ID: 20260518p43expensetrigger
Revises: 20260518p43twinhabit
Create Date: 2026-05-18 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260518p43expensetrigger"
down_revision = "20260518p43twinhabit"
branch_labels = None
depends_on = None


_SEGMENT_TRIGGERS = {
    "starter": 100_000,
    "young_pro": 500_000,
    "mass_affluent": 2_000_000,
    "hnw": 10_000_000,
}


def upgrade() -> None:
    op.add_column(
        "twin_delta_threshold_config",
        sa.Column(
            "expense_recompute_trigger_vnd",
            sa.Numeric(20, 2),
            server_default=sa.text("100000"),
            nullable=False,
        ),
    )
    for segment, amount in _SEGMENT_TRIGGERS.items():
        op.execute(
            sa.text(
                "UPDATE twin_delta_threshold_config "
                "SET expense_recompute_trigger_vnd = :amount "
                "WHERE wealth_segment = :segment"
            ).bindparams(amount=amount, segment=segment)
        )


def downgrade() -> None:
    op.drop_column("twin_delta_threshold_config", "expense_recompute_trigger_vnd")
