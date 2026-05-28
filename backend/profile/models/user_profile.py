from __future__ import annotations

import uuid
from datetime import datetime, time

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, Time
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


AGE_RANGES = ("20-29", "30-39", "40-49", "50+")


class UserProfile(Base):
    """Small editable profile overlay.

    Most profile data is derived from existing assets, transactions,
    goals, and activity. This table only stores the few fields users are
    allowed to edit in Phase 3.8.5.
    """

    __tablename__ = "user_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True
    )
    display_name: Mapped[str | None] = mapped_column(String(50))
    age_range: Mapped[str | None] = mapped_column(String(10))
    briefing_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    briefing_time: Mapped[time] = mapped_column(
        Time, default=time(7, 0), nullable=False
    )
    reminder_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    reminder_time: Mapped[time] = mapped_column(
        Time, default=time(9, 0), nullable=False
    )
    default_expense_source: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "age_range IS NULL OR age_range IN ('20-29', '30-39', '40-49', '50+')",
            name="ck_user_profiles_age_range",
        ),
    )
