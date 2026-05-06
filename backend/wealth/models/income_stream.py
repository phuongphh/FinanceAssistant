import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class IncomeStream(Base):
    """Recurring income source — salary, freelance, dividend, rental,
    interest, other.

    Phase 3.8 Epic 2 promotes streams from a flat ``amount_monthly``
    field to ``(amount, schedule_type)`` so quarterly dividends and
    annual interest don't need to be hand-converted to monthly by the
    user. The ``monthly_equivalent`` property does the math in one
    place for every reader.

    JSONB ``extra`` carries non-stream-defining metadata that varies
    per type — e.g. rental occupancy snapshot, FX rate when amount
    was entered in USD. Things that affect the stream's identity
    (type, schedule, amount) are first-class columns.

    Lifecycle:
    - ``is_active`` — paused/resumed by the user (or by Epic 1 when a
      tenant moves out). Reversible.
    - ``end_date`` — stream ended (e.g. employment ended, dividend
      stock sold). One-way.

    Layer contract: service flushes only — caller commits.
    """
    __tablename__ = "income_streams"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    # --- Classification --------------------------------------------
    # ``stream_type`` mirrors the YAML config in
    # ``content/income_types.yaml`` — values: salary | freelance |
    # dividend | rental | interest | other. We keep it as a string
    # rather than enum so adding a new type only needs a YAML edit.
    stream_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # Stored explicitly (not derived) so the agent's "thu nhập thụ
    # động" filter is a single index-friendly predicate. Default
    # derived from stream_type at create time but the user can override
    # for ambiguous cases (e.g. a salary that's actually mostly bonus).
    is_passive: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # --- Identity --------------------------------------------------
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    # --- Amount + currency -----------------------------------------
    # Raw amount in the user's chosen schedule. For "annual dividend
    # 10tr", ``amount=10_000_000`` and ``schedule_type='annually'``.
    # ``monthly_equivalent`` does the conversion for aggregations.
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    currency: Mapped[str] = mapped_column(
        String(10), default="VND", nullable=False
    )

    # --- Schedule --------------------------------------------------
    schedule_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # 1-31. Optional even for monthly — many users don't know the exact
    # day, e.g. salary "around the 5th". Reminders (Epic 3) need this;
    # totals don't.
    schedule_day: Mapped[int | None] = mapped_column(Integer)
    # 1-12 for annual streams.
    schedule_month: Mapped[int | None] = mapped_column(Integer)

    # --- Lifecycle -------------------------------------------------
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # --- Linkage ---------------------------------------------------
    # Promoted from JSONB to a real FK in Epic 2 — was
    # ``extra->>'source_asset_id'`` in Epic 1's rental wiring. ``ON
    # DELETE SET NULL`` so deleting an asset doesn't cascade-kill the
    # historical income stream.
    source_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="SET NULL")
    )

    extra: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        Index("idx_income_user_active_streams", "user_id", "is_active"),
        Index("idx_income_streams_user_type", "user_id", "stream_type", "is_active"),
        # Partial index — only rental streams populate source_asset_id.
        Index(
            "idx_income_source_asset",
            "source_asset_id",
            postgresql_where="source_asset_id IS NOT NULL",
        ),
    )

    @property
    def monthly_equivalent(self) -> Decimal:
        """Normalise ``amount`` to a monthly figure based on
        ``schedule_type``.

        - monthly    → amount
        - quarterly  → amount / 3
        - annually   → amount / 12
        - ad_hoc     → amount  (placeholder; spec wants 6-month-receipt
          average once we have IncomeRecord history wired in. Until
          then, treating ad-hoc as "expected monthly" matches the
          mental model users use when entering it.)
        """
        amount = Decimal(self.amount or 0)
        if self.schedule_type == "monthly":
            return amount
        if self.schedule_type == "quarterly":
            return amount / Decimal(3)
        if self.schedule_type == "annually":
            return amount / Decimal(12)
        # ad_hoc and any unknown schedule fall through to amount-as-is.
        return amount
