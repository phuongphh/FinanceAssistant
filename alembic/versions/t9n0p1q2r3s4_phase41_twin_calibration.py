"""phase4.1 twin calibration snapshots

Revision ID: t9n0p1q2r3s4
Revises: s8m9n0p1q2r3
Create Date: 2026-05-12 00:00:02.000000

Phase 4.1 — Story B.2. Log every Twin compute with 3 horizons so the
calibration worker can fill ``actual_vnd`` later and the view can show
hit-rate honestly ("Bé Tiền đoán đúng 7/9 lần (78%)").
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "t9n0p1q2r3s4"
down_revision = "s8m9n0p1q2r3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "twin_calibration_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("predicted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("p10_vnd", sa.Numeric(20, 2), nullable=False),
        sa.Column("p50_vnd", sa.Numeric(20, 2), nullable=False),
        sa.Column("p90_vnd", sa.Numeric(20, 2), nullable=False),
        sa.Column("actual_vnd", sa.Numeric(20, 2), nullable=True),
        sa.Column("actual_recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("within_band", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )

    # Partial index — worker only ever scans rows whose actual hasn't
    # landed yet. Keeps the scan O(due rows) regardless of history size.
    op.execute(
        "CREATE INDEX idx_twin_calibration_due "
        "ON twin_calibration_snapshots (predicted_at, horizon_days) "
        "WHERE actual_vnd IS NULL"
    )
    op.create_index(
        "idx_twin_calibration_user",
        "twin_calibration_snapshots",
        ["user_id", "predicted_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_twin_calibration_user", table_name="twin_calibration_snapshots"
    )
    op.execute("DROP INDEX IF EXISTS idx_twin_calibration_due")
    op.drop_table("twin_calibration_snapshots")
