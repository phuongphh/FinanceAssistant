"""phase4b twin accuracy tracking

Revision ID: 20260811p4baccuracy
Revises: 20260720p4atwin
Create Date: 2026-08-11 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260811p4baccuracy"
down_revision = "20260720p4atwin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "twin_projections",
        sa.Column("actual_net_worth", sa.Numeric(20, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("twin_projections", "actual_net_worth")
