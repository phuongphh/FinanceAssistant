"""phase4.1 user cost budgets + llm cost log

Revision ID: r7l8m9n0p1q2
Revises: q6k7l8m9n0p1
Create Date: 2026-05-12 00:00:00.000000

Phase 4.1 — Pre-Launch Hardening, Story A.3.

Adds per-user monthly budget cap + per-call LLM cost log so we can
stop a runaway user before the bill arrives. v1 tiers are limited to
``free`` and ``pro`` via CHECK constraint — Max defers to Phase 5.7.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "r7l8m9n0p1q2"
down_revision = "20261201rentalname"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_cost_budgets",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            primary_key=True,
        ),
        sa.Column(
            "tier",
            sa.String(length=16),
            server_default=sa.text("'free'"),
            nullable=False,
        ),
        sa.Column("monthly_cap_vnd", sa.Numeric(15, 2), nullable=False),
        sa.Column(
            "current_month_spend_vnd",
            sa.Numeric(15, 2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("current_month_started_at", sa.Date(), nullable=False),
        sa.Column("last_warning_sent_at", sa.DateTime(timezone=True), nullable=True),
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
        # v1 scope: only free / pro. Max is reserved for Phase 5.7+, when
        # feature gates exist. Constraint dropped + replaced in that phase.
        sa.CheckConstraint(
            "tier IN ('free', 'pro')",
            name="chk_tier_v1",
        ),
    )

    op.create_table(
        "llm_cost_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("tokens_in", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("tokens_out", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("cost_vnd", sa.Numeric(15, 4), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("success", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_llm_cost_log_user_day",
        "llm_cost_log",
        ["user_id", "created_at"],
    )
    op.create_index(
        "idx_llm_cost_log_provider_day",
        "llm_cost_log",
        ["provider", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_llm_cost_log_provider_day", table_name="llm_cost_log")
    op.drop_index("idx_llm_cost_log_user_day", table_name="llm_cost_log")
    op.drop_table("llm_cost_log")
    op.drop_table("user_cost_budgets")
