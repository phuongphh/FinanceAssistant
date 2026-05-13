"""phase4b life events table and twin base cone column

Revision ID: 20260911p4bevents
Revises: 20260811p4baccuracy
Create Date: 2026-09-11 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260911p4bevents"
down_revision = "20260811p4baccuracy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "life_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=200)),
        sa.Column("planned_date", sa.Date()),
        sa.Column("one_time_cost", sa.Numeric(20, 2)),
        sa.Column("recurring_monthly_delta", sa.Numeric(20, 2)),
        sa.Column("recurring_duration_months", sa.Integer()),
        sa.Column("notes", sa.Text()),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("TRUE"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.execute(
        "CREATE INDEX life_events_user_active_idx ON life_events(user_id) "
        "WHERE deleted_at IS NULL AND is_active = TRUE"
    )

    # base_cone_data lets the Mini App diff "with / without event X" without
    # re-running Monte Carlo. Nullable because pre-Epic-2 rows didn't compute it.
    op.add_column(
        "twin_projections",
        sa.Column(
            "base_cone_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("twin_projections", "base_cone_data")
    op.execute("DROP INDEX IF EXISTS life_events_user_active_idx")
    op.drop_table("life_events")
