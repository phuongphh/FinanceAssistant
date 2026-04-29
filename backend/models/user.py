from __future__ import annotations

import uuid
from datetime import datetime, time

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, Numeric, String, Time
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    telegram_handle: Mapped[str | None] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(255))
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Ho_Chi_Minh")
    currency: Mapped[str] = mapped_column(String(10), default="VND")
    monthly_income: Mapped[float | None] = mapped_column(Numeric(15, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Phase 2 — Onboarding
    primary_goal: Mapped[str | None] = mapped_column(String(30))
    onboarding_step: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    onboarding_skipped: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    onboarding_skipped_asset: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # Phase 3A — Wealth foundation
    primary_currency: Mapped[str] = mapped_column(String(3), default="VND", nullable=False)
    wealth_level: Mapped[str | None] = mapped_column(String(20))
    expense_threshold_micro: Mapped[int] = mapped_column(
        Integer, default=200_000, nullable=False
    )
    expense_threshold_major: Mapped[int] = mapped_column(
        Integer, default=2_000_000, nullable=False
    )
    briefing_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    briefing_time: Mapped[time] = mapped_column(
        Time, default=time(7, 0), nullable=False
    )
    # Multi-step wizard scratch space (asset entry etc).
    # Shape: {"flow": "asset_add_cash", "step": "amount", "draft": {...}}
    wizard_state: Mapped[dict | None] = mapped_column(JSONB)

    @property
    def is_onboarded(self) -> bool:
        """True once the user has either finished or explicitly skipped."""
        return self.onboarding_completed_at is not None or self.onboarding_skipped

    def get_greeting_name(self) -> str:
        """Name to address the user by — falls back to 'bạn' (Vietnamese)."""
        name = (self.display_name or "").strip()
        return name if name else "bạn"
