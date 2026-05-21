from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    amount: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    transaction_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="expense", server_default="expense"
    )
    currency: Mapped[str] = mapped_column(String(10), default="VND")
    merchant: Mapped[str | None] = mapped_column(String(500))
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    source_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="SET NULL")
    )
    source_credit_card_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("credit_cards.id", ondelete="SET NULL")
    )
    source_type: Mapped[str | None] = mapped_column(String(30))
    e_wallet_provider: Mapped[str | None] = mapped_column(String(30))
    expense_date: Mapped[date] = mapped_column(Date, nullable=False)
    month_key: Mapped[str] = mapped_column(String(7), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    raw_data: Mapped[dict | None] = mapped_column(JSONB)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    gmail_message_id: Mapped[str | None] = mapped_column(String(255))

    # Phase 3.8 Epic 3 — link a transaction to its recurring pattern.
    # ``is_recurring`` is denormalised from ``recurrence_id IS NOT
    # NULL`` so the agent can filter "khoản định kỳ tháng này"
    # without joining recurring_patterns. Both fields default safe
    # for the 95% of one-off transactions.
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    recurrence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recurring_patterns.id", ondelete="SET NULL"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("idx_expenses_month_key", "user_id", "month_key"),
        Index("idx_expenses_category", "user_id", "category"),
        Index("idx_expenses_type_month", "user_id", "transaction_type", "month_key"),
        Index(
            "idx_expenses_source_asset",
            "source_asset_id",
            postgresql_where=text("source_asset_id IS NOT NULL"),
        ),
        Index(
            "idx_expenses_gmail_id",
            "gmail_message_id",
            postgresql_where=text("gmail_message_id IS NOT NULL"),
        ),
        # Phase 3.8 Epic 3 — partial index for "was this period
        # already paid?" lookups. Most rows have no recurrence_id so
        # the partial keeps the index small.
        Index(
            "idx_expenses_recurrence",
            "recurrence_id",
            "expense_date",
            postgresql_where=text("recurrence_id IS NOT NULL"),
        ),
    )
