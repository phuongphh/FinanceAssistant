from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base

PLAN_FREE = "free"
PLAN_PRO = "pro"
PLAN_FOUNDING = "founding"
PLAN_ENTERPRISE = "enterprise"
LICENSE_PLANS = {PLAN_FREE, PLAN_PRO, PLAN_FOUNDING, PLAN_ENTERPRISE}

STATUS_ACTIVE = "active"
STATUS_TRIALING = "trialing"
STATUS_PAST_DUE = "past_due"
STATUS_CANCELED = "canceled"
STATUS_EXPIRED = "expired"
LICENSE_STATUSES = {
    STATUS_ACTIVE,
    STATUS_TRIALING,
    STATUS_PAST_DUE,
    STATUS_CANCELED,
    STATUS_EXPIRED,
}


class License(Base):
    """Phase 4.2.5 foundation for future monetization state.

    v1 only reads aggregate license counts in the admin console. Mutation flows
    remain deferred until Phase 5.7 so there is no customer-facing entitlement
    enforcement yet.
    """

    __tablename__ = "licenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    tenant_id: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False, index=True
    )
    plan: Mapped[str] = mapped_column(
        String(50), default=PLAN_FREE, nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(50), default=STATUS_ACTIVE, nullable=False, index=True
    )
    trial_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user = relationship("User")
