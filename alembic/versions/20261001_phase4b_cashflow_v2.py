"""phase4b epic3 — cashflow forecasting v2

Revision ID: 20261001p4bcashflow
Revises: 20260911p4bevents
Create Date: 2026-10-01 00:00:00.000000

Phase 4B Epic 3 (Stories P4B-S14..S20):

1. Extends ``recurring_patterns`` with Phase 4B columns:
   - ``pattern_type`` — 'income' | 'expense' (detector now handles both)
   - ``confidence`` — detection confidence score [0.0, 1.0]
   - ``is_confirmed`` — alias semantic for ``user_confirmed`` column added in
     Phase 3.8; we add the new column rather than rename to avoid breaking
     existing application code that reads ``user_confirmed``.
   - ``dismissed_until`` — snooze-style dedup (don't re-prompt for 30 days)
   - ``first_seen_at``, ``last_seen_at`` — detection lifecycle timestamps
   - ``description`` — human-readable pattern label for UI display

2. Creates ``cashflow_forecasts`` — daily snapshot of 3-month rolling
   cashflow projection built from confirmed recurring patterns.

3. Extends ``users`` with ``cashflow_alert_threshold`` — user-customisable
   floor; alerts fire when any forecasted month-end balance drops below it.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261001p4bcashflow"
down_revision = "20260911p4bevents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Extend recurring_patterns for Phase 4B cashflow detector
    # ------------------------------------------------------------------
    # pattern_type distinguishes income patterns (salary) from expense
    # patterns (rent). Phase 3.8 assumed all patterns were expenses;
    # Phase 4B adds income detection for more accurate forecasting.
    op.add_column(
        "recurring_patterns",
        sa.Column(
            "pattern_type",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'expense'"),
        ),
    )
    # Confidence scores from the detector heuristic [0.0, 1.0].
    # NULL for manually-created patterns (user entered it directly).
    op.add_column(
        "recurring_patterns",
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
    )
    # Dismiss a pattern suggestion for 30 days without rejecting it
    # permanently. NULL = not dismissed.
    op.add_column(
        "recurring_patterns",
        sa.Column("dismissed_until", sa.DateTime(timezone=True), nullable=True),
    )
    # Detection lifecycle — when did the detector first/last see this
    # pattern in the transaction history?
    op.add_column(
        "recurring_patterns",
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "recurring_patterns",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Human-readable description used in Telegram review messages and
    # Mini App pattern list. Complements the existing ``name`` column.
    op.add_column(
        "recurring_patterns",
        sa.Column("description", sa.String(200), nullable=True),
    )

    # Partial index for cashflow forecast queries — only confirmed
    # patterns feed into the 3-month projection.
    op.create_index(
        "idx_patterns_confirmed_cashflow",
        "recurring_patterns",
        ["user_id", "pattern_type"],
        postgresql_where=sa.text("user_confirmed = true AND is_active = true"),
    )

    # ------------------------------------------------------------------
    # cashflow_forecasts — daily 3-month rolling projection snapshot
    # ------------------------------------------------------------------
    op.create_table(
        "cashflow_forecasts",
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
        # The calendar date for which this forecast was computed (today
        # at compute time). Used as dedup key + history anchor.
        sa.Column("forecast_date", sa.Date(), nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "horizon_months",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("3"),
        ),
        # JSONB stores List[MonthlyForecastData] — each item has:
        # month, income, expense, net, balance_eom.
        sa.Column(
            "monthly_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        # Alert flags — pre-computed so the morning briefing can check
        # low_balance_risk without re-running the forecast.
        sa.Column(
            "low_balance_risk",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("low_balance_month", sa.Date(), nullable=True),
        sa.Column("low_balance_threshold", sa.Numeric(20, 2), nullable=True),
        # Version tag so we can replay with updated logic without
        # invalidating existing rows.
        sa.Column(
            "engine_version",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'1.0'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_cashflow_forecasts_user_date",
        "cashflow_forecasts",
        ["user_id", "forecast_date"],
        # DESC on forecast_date so "get latest" queries use the index
        # without a sort step. PostgreSQL DESC index semantics apply.
    )

    # ------------------------------------------------------------------
    # users — cashflow_alert_threshold (user-customisable, nullable)
    # ------------------------------------------------------------------
    op.add_column(
        "users",
        sa.Column("cashflow_alert_threshold", sa.Numeric(20, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "cashflow_alert_threshold")

    op.drop_index("idx_cashflow_forecasts_user_date", table_name="cashflow_forecasts")
    op.drop_table("cashflow_forecasts")

    op.drop_index("idx_patterns_confirmed_cashflow", table_name="recurring_patterns")
    op.drop_column("recurring_patterns", "description")
    op.drop_column("recurring_patterns", "last_seen_at")
    op.drop_column("recurring_patterns", "first_seen_at")
    op.drop_column("recurring_patterns", "dismissed_until")
    op.drop_column("recurring_patterns", "confidence")
    op.drop_column("recurring_patterns", "pattern_type")
