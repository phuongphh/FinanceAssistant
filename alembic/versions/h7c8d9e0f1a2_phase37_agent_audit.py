"""phase 3.7 — agent_audit_logs table

Revision ID: h7c8d9e0f1a2
Revises: g6b7c8d9e0f1
Create Date: 2026-05-05 00:00:00.000000

Per-call audit log for the Phase 3.7 agent system. One row per
``Orchestrator.route()`` invocation. Captures routing decision,
tool usage, LLM accounting, and outcome. Indexed for the two query
shapes the admin dashboard runs:
- ``WHERE tier_used = ? AND query_timestamp >= ?`` (tier-by-day)
- ``ORDER BY total_latency_ms DESC LIMIT 10`` (slow-query hunt)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "h7c8d9e0f1a2"
down_revision: Union[str, Sequence[str], None] = "g6b7c8d9e0f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_audit_logs",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        # Nullable: a few agent calls (admin dry-runs, system probes)
        # may not be tied to a real user.
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("query_text", sa.String(2000), nullable=True),
        sa.Column(
            "query_timestamp", sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"), nullable=False,
        ),
        sa.Column("tier_used", sa.String(20), nullable=False),
        sa.Column("routing_reason", sa.String(100), nullable=True),
        sa.Column("tools_called", postgresql.JSONB(), nullable=True),
        sa.Column(
            "tool_call_count", sa.Integer(),
            server_default=sa.text("0"), nullable=False,
        ),
        sa.Column("llm_model", sa.String(50), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=True),
        sa.Column(
            "success", sa.Boolean(),
            server_default=sa.text("FALSE"), nullable=False,
        ),
        sa.Column("response_preview", sa.String(500), nullable=True),
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("total_latency_ms", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_audit_logs_user_id", "agent_audit_logs", ["user_id"]
    )
    op.create_index(
        "ix_agent_audit_logs_query_timestamp",
        "agent_audit_logs",
        ["query_timestamp"],
    )
    op.create_index(
        "idx_agent_audit_tier_time",
        "agent_audit_logs",
        ["tier_used", "query_timestamp"],
    )
    op.create_index(
        "idx_agent_audit_latency",
        "agent_audit_logs",
        ["total_latency_ms"],
    )


def downgrade() -> None:
    op.drop_index("idx_agent_audit_latency", table_name="agent_audit_logs")
    op.drop_index("idx_agent_audit_tier_time", table_name="agent_audit_logs")
    op.drop_index(
        "ix_agent_audit_logs_query_timestamp", table_name="agent_audit_logs"
    )
    op.drop_index("ix_agent_audit_logs_user_id", table_name="agent_audit_logs")
    op.drop_table("agent_audit_logs")
