"""phase 4.5 decision query log (E5 #5.1)

Append-only log of every Decision-Engine question (shock simulation, plan
feasibility). One row per handled query — including the clarify/empty/confirm
turns that never reach a verdict, which land as ``success=False`` so the funnel
shows where users stall. Feeds the G1/G2 gates now and the Phase 4.6 admin
dashboard chart later; this phase only writes.

Three secondary indexes match the three ways the dashboard slices the log:
per-user, per-query-type, and over time.

Revision ID: 20260710dqlog45
Revises: 20260710tone45
Create Date: 2026-07-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


revision = "20260710dqlog45"
down_revision = "20260710tone45"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "decision_query_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("query_type", sa.String(length=32), nullable=False),
        sa.Column("clarity_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_decision_query_log_user_id", "decision_query_logs", ["user_id"]
    )
    op.create_index(
        "idx_decision_query_log_query_type", "decision_query_logs", ["query_type"]
    )
    op.create_index(
        "idx_decision_query_log_created_at", "decision_query_logs", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("idx_decision_query_log_created_at", "decision_query_logs")
    op.drop_index("idx_decision_query_log_query_type", "decision_query_logs")
    op.drop_index("idx_decision_query_log_user_id", "decision_query_logs")
    op.drop_table("decision_query_logs")
