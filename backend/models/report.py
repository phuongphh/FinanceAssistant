from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class MonthlyReport(Base):
    __tablename__ = "monthly_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    month_key: Mapped[str] = mapped_column(String(7), nullable=False)
    total_expense: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    total_income: Mapped[float | None] = mapped_column(Numeric(15, 2))
    savings_amount: Mapped[float | None] = mapped_column(Numeric(15, 2))
    savings_rate: Mapped[float | None] = mapped_column(Numeric(5, 2))
    breakdown_by_category: Mapped[dict] = mapped_column(JSONB, nullable=False)
    vs_previous_month: Mapped[dict | None] = mapped_column(JSONB)
    goal_progress: Mapped[dict | None] = mapped_column(JSONB)
    report_text: Mapped[str | None] = mapped_column(Text)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )

    __table_args__ = (
        UniqueConstraint("user_id", "month_key", name="uq_report_user_month"),
    )
