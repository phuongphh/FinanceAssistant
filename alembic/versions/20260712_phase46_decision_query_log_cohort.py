"""phase 4.6 decision query log cohort tag (E4 #4.1)

Adds an onboarding-cohort tag to the append-only decision-query log so the
Phase 4.6 admin dashboard can split the new first-life segment (22-35,
Level 0→1) from the legacy asset-management cohort. ``cohort`` is a short
stable code ("reset" / "legacy") derived from the chosen goal, NULL when the
goal is unknown or no session exists. A single-column index matches the
dashboard's per-cohort grouping.

Purely additive: a nullable column + one index. No backfill — pre-existing
rows keep a NULL cohort, which the chart reads as "unattributed".

Revision ID: 20260712dqcohort46
Revises: 20260710dqlog45
Create Date: 2026-07-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260712dqcohort46"
down_revision = "20260710dqlog45"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "decision_query_logs",
        sa.Column("cohort", sa.String(length=16), nullable=True),
    )
    op.create_index(
        "idx_decision_query_log_cohort", "decision_query_logs", ["cohort"]
    )


def downgrade() -> None:
    op.drop_index("idx_decision_query_log_cohort", "decision_query_logs")
    op.drop_column("decision_query_logs", "cohort")
