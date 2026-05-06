"""Recurring expense pattern — Phase 3.8 Epic 3.

A pattern represents a *commitment* (rent, internet, gym, Netflix)
that recurs on a regular schedule. The bot remembers patterns so it
can:
- Send reminders 2 days before the due date.
- Match incoming transactions to the pattern (so cashflow forecast
  knows the expense is already accounted for).
- Avoid re-detecting the same recurring expense via the nightly
  ``RecurringDetector`` scan.

Two creation paths feed this table:
- **Manual** — user enters via the menu wizard (Chi tiêu →
  🔄 Khoản định kỳ → ➕ Thêm).
- **Auto-detected** — ``RecurringDetector`` analyses 6 months of
  history, suggests patterns, user confirms with a tap.

The ``auto_detected`` flag preserves which path created the row —
useful for analytics and for the future "suggest re-detection" UX.

Layer contract: service flushes only — caller commits.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class RecurringPattern(Base):
    __tablename__ = "recurring_patterns"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    # --- Pattern identity ------------------------------------------
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    expected_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    # ± tolerance for matching transactions to this pattern. Default
    # 10% covers a small rent increase ("rent went up 5%") without
    # the detector re-suggesting the pattern from scratch.
    amount_variance_pct: Mapped[float] = mapped_column(
        Float, default=10.0, nullable=False
    )

    # --- Schedule --------------------------------------------------
    schedule_type: Mapped[str] = mapped_column(
        String(20), default="monthly", nullable=False
    )
    expected_day_of_month: Mapped[int | None] = mapped_column(Integer)

    # --- State -----------------------------------------------------
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auto_detected: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    user_confirmed: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # --- Reminders -------------------------------------------------
    enable_reminders: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    reminder_days_before: Mapped[int] = mapped_column(
        Integer, default=2, nullable=False
    )
    last_reminder_sent: Mapped[date | None] = mapped_column(Date)
    # Snooze-until — set by the "trễ vài ngày" callback. Scheduler
    # skips this pattern until ``date.today() > snooze_until``.
    snooze_until: Mapped[date | None] = mapped_column(Date)

    # --- Tracking --------------------------------------------------
    last_occurrence_date: Mapped[date | None] = mapped_column(Date)
    occurrence_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        Index("idx_patterns_user_active", "user_id", "is_active"),
        Index(
            "idx_patterns_due_soon",
            "user_id", "expected_day_of_month",
            postgresql_where=text(
                "is_active = true AND enable_reminders = true"
            ),
        ),
    )


class PatternSuggestionLog(Base):
    """Append-only log of auto-detected suggestions delivered to users.

    Two roles:
    - **De-spam guard** — the detector consults this table; if a
      fingerprint was rejected within the last 90 days, we skip it.
      Without this, every nightly run would re-suggest the same
      pattern the user already said no to.
    - **Audit / analytics** — accept/reject ratios drive the
      detector's confidence calibration in future phases.

    ``fingerprint`` is the dedup key. Two suggestions count as the
    "same" if their fingerprint matches — see ``RecurringDetector
    ._fingerprint`` for the definition.
    """

    __tablename__ = "pattern_suggestions_log"

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    fingerprint: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    suggested_amount: Mapped[Decimal] = mapped_column(
        Numeric(20, 2), nullable=False
    )
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False)
    typical_day: Mapped[int | None] = mapped_column(Integer)

    # Outcome — null when first sent, set when user reacts.
    # Values: accepted | rejected | ignored | edited.
    outcome: Mapped[str | None] = mapped_column(String(20))
    pattern_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recurring_patterns.id", ondelete="SET NULL"),
    )

    suggested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index(
            "idx_suggestions_user_fingerprint",
            "user_id", "fingerprint", "suggested_at",
        ),
    )
