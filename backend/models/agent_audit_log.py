"""Agent audit log — one row per Tier 1/2/3 query.

Why a dedicated table instead of reusing ``events``:
- Per-call structured fields (tools_called JSON, latency, cost) are
  first-class queryable. ``SELECT SUM(cost_usd) FROM agent_audit_logs
  WHERE query_timestamp >= today`` beats ``WHERE properties->>'cost' …``.
- Cost / latency dashboards have a single denormalised source.
- Doesn't dilute the ``events`` stream which is funnels-and-flags.

PII note: ``query_text`` is the raw user input. For Phase 0/1 (owner
only) this is fine; for Phase 1+ multi-user, swap with a one-way hash
or sample-rate the field. Document in CLAUDE.md before opening up.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class AgentAuditLog(Base):
    """One agent invocation. Append-only — never edit a row."""

    __tablename__ = "agent_audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Nullable to mirror ``events`` (some agent calls happen for
    # not-yet-resolved users; rare but possible).
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )

    # Raw query — see PII note in module docstring. 2000 chars is
    # enough for any free-form input we accept (Telegram caps at 4096
    # but those are voice transcripts at most).
    query_text: Mapped[str | None] = mapped_column(String(2000))
    query_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow,
        nullable=False, index=True,
    )

    # Routing decision.
    tier_used: Mapped[str] = mapped_column(String(20), nullable=False)
    routing_reason: Mapped[str | None] = mapped_column(String(100))

    # Tool usage. Each entry: {name, args, latency_ms, error?}.
    tools_called: Mapped[list | None] = mapped_column(JSONB)
    tool_call_count: Mapped[int] = mapped_column(Integer, default=0)

    # LLM accounting.
    llm_model: Mapped[str | None] = mapped_column(String(50))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    # Numeric(10, 6) → up to $9999.999999, plenty of precision.
    cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 6))

    # Outcome.
    success: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # 500 chars = enough to grok the answer in a debug session
    # without turning the table into a content store.
    response_preview: Mapped[str | None] = mapped_column(String(500))
    error: Mapped[str | None] = mapped_column(String(500))

    # Performance.
    total_latency_ms: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        # Tier-by-day aggregations (e.g. "Tier 3 cost today").
        Index("idx_agent_audit_tier_time", "tier_used", "query_timestamp"),
        # Slow-query hunting.
        Index("idx_agent_audit_latency", "total_latency_ms"),
    )
