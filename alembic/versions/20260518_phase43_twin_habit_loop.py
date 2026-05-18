"""phase4.3 epic3 twin habit loop

Revision ID: 20260518p43twinhabit
Revises: 20260518p43twinstory
Create Date: 2026-05-18 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260518p43twinhabit"
down_revision = "20260518p43twinstory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "twin_recompute_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.String(length=80), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("queue_ms", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("compute_ms", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("notify_ms", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("total_ms", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("delta_pct", sa.Numeric(10, 4), server_default=sa.text("0"), nullable=False),
        sa.Column("delta_absolute_vnd", sa.Numeric(20, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("notified_bool", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False),
        sa.Column("skip_reason", sa.String(length=80), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_twin_recompute_user_created", "twin_recompute_log", ["user_id", "created_at"])
    op.create_index("idx_twin_recompute_event", "twin_recompute_log", ["event_id"])

    op.create_table(
        "twin_delta_threshold_config",
        sa.Column("wealth_segment", sa.String(length=40), nullable=False),
        sa.Column("positive_threshold_pct", sa.Numeric(8, 4), nullable=False),
        sa.Column("positive_threshold_absolute_vnd", sa.Numeric(20, 2), nullable=False),
        sa.Column("negative_threshold_pct", sa.Numeric(8, 4), nullable=False),
        sa.Column("negative_threshold_absolute_vnd", sa.Numeric(20, 2), nullable=False),
        sa.Column("updated_by", sa.String(length=80), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("wealth_segment"),
    )
    op.bulk_insert(
        sa.table(
            "twin_delta_threshold_config",
            sa.column("wealth_segment", sa.String),
            sa.column("positive_threshold_pct", sa.Numeric),
            sa.column("positive_threshold_absolute_vnd", sa.Numeric),
            sa.column("negative_threshold_pct", sa.Numeric),
            sa.column("negative_threshold_absolute_vnd", sa.Numeric),
        ),
        [
            {"wealth_segment": "starter", "positive_threshold_pct": 1.0, "positive_threshold_absolute_vnd": 1_000_000, "negative_threshold_pct": 1.0, "negative_threshold_absolute_vnd": 1_000_000},
            {"wealth_segment": "young_pro", "positive_threshold_pct": 1.0, "positive_threshold_absolute_vnd": 3_000_000, "negative_threshold_pct": 1.0, "negative_threshold_absolute_vnd": 3_000_000},
            {"wealth_segment": "mass_affluent", "positive_threshold_pct": 1.0, "positive_threshold_absolute_vnd": 10_000_000, "negative_threshold_pct": 1.0, "negative_threshold_absolute_vnd": 10_000_000},
            {"wealth_segment": "hnw", "positive_threshold_pct": 0.5, "positive_threshold_absolute_vnd": 50_000_000, "negative_threshold_pct": 0.5, "negative_threshold_absolute_vnd": 50_000_000},
        ],
    )


def downgrade() -> None:
    op.drop_table("twin_delta_threshold_config")
    op.drop_index("idx_twin_recompute_event", table_name="twin_recompute_log")
    op.drop_index("idx_twin_recompute_user_created", table_name="twin_recompute_log")
    op.drop_table("twin_recompute_log")
