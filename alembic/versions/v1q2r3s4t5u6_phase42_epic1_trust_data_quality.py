"""phase4.2 epic1 trust and data quality flags

Revision ID: v1q2r3s4t5u6
Revises: u0p1q2r3s4t5
Create Date: 2026-05-13 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "v1q2r3s4t5u6"
down_revision = "u0p1q2r3s4t5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("assets", sa.Column("is_placeholder_asset", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("assets", sa.Column("is_confirmed", sa.Boolean(), server_default=sa.text("true"), nullable=False))
    op.add_column("assets", sa.Column("source_input_raw", sa.Text(), nullable=True))
    op.add_column("assets", sa.Column("data_quality_warning_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("assets", sa.Column("data_quality_warning_type", sa.String(length=50), nullable=True))
    op.execute(
        "CREATE INDEX idx_assets_real ON assets (user_id, is_active, is_placeholder_asset, is_confirmed) "
        "WHERE is_active = TRUE AND is_placeholder_asset = FALSE AND is_confirmed = TRUE"
    )
    op.create_index("idx_assets_recent", "assets", ["user_id", "asset_type", "created_at"])

    op.add_column("onboarding_sessions", sa.Column("trust_shown_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("onboarding_sessions", sa.Column("trust_accepted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("onboarding_sessions", sa.Column("trust_question_raised_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("onboarding_sessions", sa.Column("next_best_action_taken", sa.String(length=50), nullable=True))
    op.add_column("onboarding_sessions", sa.Column("next_best_action_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("onboarding_sessions", "next_best_action_at")
    op.drop_column("onboarding_sessions", "next_best_action_taken")
    op.drop_column("onboarding_sessions", "trust_question_raised_at")
    op.drop_column("onboarding_sessions", "trust_accepted_at")
    op.drop_column("onboarding_sessions", "trust_shown_at")

    op.drop_index("idx_assets_recent", table_name="assets")
    op.execute("DROP INDEX IF EXISTS idx_assets_real")
    op.drop_column("assets", "data_quality_warning_type")
    op.drop_column("assets", "data_quality_warning_at")
    op.drop_column("assets", "source_input_raw")
    op.drop_column("assets", "is_confirmed")
    op.drop_column("assets", "is_placeholder_asset")
