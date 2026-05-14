"""Per-user LLM cost budget + per-call cost log (Phase 4.1, Story A.3).

The budget table caps how much we spend on LLM/Whisper/OCR per user
per month. The log table is the raw stream every adapter writes to —
the budget worker rolls it up, and the daily KPI digest reads it.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


TIER_FREE = "free"
TIER_PRO = "pro"

# Defaults rounded for v1. ``free`` is wide enough for a heavy classify
# day (~500 calls @ 60 VND each), ``pro`` is the placeholder Phase 5.7
# reuses. Operator can bump per-user via /budget_set.
DEFAULT_BUDGET_VND: dict[str, Decimal] = {
    TIER_FREE: Decimal("30000"),
    TIER_PRO: Decimal("100000"),
}


class UserCostBudget(Base):
    __tablename__ = "user_cost_budgets"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True
    )
    tier: Mapped[str] = mapped_column(String(16), default=TIER_FREE, nullable=False)
    monthly_cap_vnd: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    current_month_spend_vnd: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), default=Decimal("0"), nullable=False
    )
    current_month_started_at: Mapped[date] = mapped_column(Date, nullable=False)
    last_warning_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    __table_args__ = (CheckConstraint("tier IN ('free', 'pro')", name="chk_tier_v1"),)


class LLMCostLog(Base):
    __tablename__ = "llm_cost_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    tenant_id: Mapped[int] = mapped_column(Integer, default=1, nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_vnd: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
