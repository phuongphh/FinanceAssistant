"""phase4a twin projections

Revision ID: 20260720p4atwin
Revises: q6k7l8m9n0p1
Create Date: 2026-07-20 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260720p4atwin"
down_revision = "q6k7l8m9n0p1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "twin_projections",
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
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("horizon_years", sa.Integer(), nullable=False),
        sa.Column("scenario", sa.String(length=20), nullable=False),
        sa.Column("base_net_worth", sa.Numeric(20, 2), nullable=False),
        sa.Column("monthly_savings", sa.Numeric(20, 2), nullable=False),
        sa.Column(
            "allocation_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("cone_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "sim_paths",
            sa.Integer(),
            server_default=sa.text("1000"),
            nullable=False,
        ),
        sa.Column("seed", sa.BigInteger()),
        sa.Column("engine_version", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.execute(
        "CREATE INDEX idx_twin_proj_user_latest "
        "ON twin_projections(user_id, computed_at DESC)"
    )
    op.execute(
        "CREATE INDEX idx_twin_proj_user_scenario "
        "ON twin_projections(user_id, scenario, computed_at DESC)"
    )


def downgrade() -> None:
    op.drop_index("idx_twin_proj_user_scenario", table_name="twin_projections")
    op.drop_index("idx_twin_proj_user_latest", table_name="twin_projections")
    op.drop_table("twin_projections")
