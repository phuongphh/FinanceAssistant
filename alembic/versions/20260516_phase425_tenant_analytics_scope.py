"""Phase 4.2.5 tenant scope for analytics sources

Revision ID: 20260516p425tenant
Revises: 20260515p425events
Create Date: 2026-05-16 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260516p425tenant"
down_revision: Union[str, Sequence[str], None] = "20260515p425events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLES = (
    "users",
    "events",
    "portfolio_assets",
    "llm_cost_log",
    "agent_audit_logs",
)


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column("tenant_id", sa.Integer(), nullable=False, server_default="1"),
        )
        op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])

    op.create_index(
        "idx_events_tenant_type_time",
        "events",
        ["tenant_id", "event_type", "timestamp"],
    )
    op.create_index(
        "idx_portfolio_tenant_user",
        "portfolio_assets",
        ["tenant_id", "user_id"],
    )
    op.create_index(
        "idx_agent_audit_tenant_time",
        "agent_audit_logs",
        ["tenant_id", "query_timestamp"],
    )


def downgrade() -> None:
    op.drop_index("idx_agent_audit_tenant_time", table_name="agent_audit_logs")
    op.drop_index("idx_portfolio_tenant_user", table_name="portfolio_assets")
    op.drop_index("idx_events_tenant_type_time", table_name="events")

    for table in reversed(_TABLES):
        op.drop_index(f"ix_{table}_tenant_id", table_name=table)
        op.drop_column(table, "tenant_id")
