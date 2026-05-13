"""Goal — Phase 3.8 Epic 5 extension of the Phase 3A stub.

A Goal is a target the user wants to hit (e.g. "Mua xe 800tr in 2
years", "Quỹ khẩn cấp 100tr"). Two creation paths feed this table:

- **Template wizard** — user picks one of 7 presets from
  ``content/goal_templates.yaml``. ``template_id`` carries the
  preset id (e.g. ``buy_car``) and ``icon`` mirrors the YAML icon.
- **Custom** — user describes their own goal. ``template_id`` stays
  null; ``icon`` falls back to ``🎯`` in the formatter.

Lifecycle via ``status``:
- ``active``     — being pursued (default)
- ``completed``  — current_amount ≥ target_amount; ``completed_at``
  set so we can celebrate at the right moment
- ``paused``     — user stopped contributing but might resume
- ``abandoned``  — user gave up; preserved for history

The ``monthly_savings_required`` cache is populated by
``GoalProjectionService.project_goal`` so the list view can render
"cần X/tháng" without recomputing on every tap.

Layer contract: model only — no business logic. Service layer
(``goal_service`` / ``goal_projection``) does mutations.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )

    # --- Template linkage ----------------------------------------
    # Mirrors the YAML key in ``content/goal_templates.yaml``. Null
    # for custom goals. We keep the snapshot of ``icon`` on the row
    # rather than re-resolving from the template at read time —
    # that way YAML edits don't retroactively change a user's goal
    # display.
    template_id: Mapped[str | None] = mapped_column(String(50))
    icon: Mapped[str | None] = mapped_column(String(20))

    # --- Identity ------------------------------------------------
    name: Mapped[str] = mapped_column(String(500), nullable=False)

    # --- Target + progress ---------------------------------------
    # ``target_amount`` and ``current_amount`` use ``Numeric(20,2)``
    # to fit "Mua nhà 10 tỷ" and "hưu trí 20 tỷ" goals — Phase 3A's
    # 15,2 capped at 9.99 trillion which Mass Affluent users will
    # hit.
    target_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    current_amount: Mapped[Decimal] = mapped_column(
        Numeric(20, 2), default=0, nullable=False
    )
    target_date: Mapped[date | None] = mapped_column(Date)

    # --- Strategy cache ------------------------------------------
    # Populated by ``GoalProjectionService``. Null when the goal has
    # no target_date (open-ended goal — projection computes
    # ``estimated_completion_date`` instead).
    monthly_savings_required: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 2)
    )

    # --- State ---------------------------------------------------
    # Stored as a string rather than enum so adding 'snoozed' or
    # 'won' later is a value-set change, not a schema migration.
    status: Mapped[str] = mapped_column(
        String(20), default="active", nullable=False
    )
    # 1=highest, 10=lowest. Multi-goal ranking (Phase 4) reads this.
    priority: Mapped[int] = mapped_column(Integer, default=5, nullable=False)

    # --- Linkage -------------------------------------------------
    # Phase 4 will let users tag specific cash assets ("count my
    # VCB savings toward 'quỹ khẩn cấp'"). Stored as a JSON list of
    # asset UUIDs; nullable until that phase wires it.
    linked_assets: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index(
            "idx_goals_user_status_priority",
            "user_id", "status", "priority",
        ),
    )

    @property
    def progress_pct(self) -> float:
        """0-100 progress percentage. ``0`` when target_amount is 0
        (defensive — should never happen via wizard, but a stray
        ``UPDATE`` could leave it that way)."""
        target = Decimal(self.target_amount or 0)
        if target <= 0:
            return 0.0
        current = Decimal(self.current_amount or 0)
        return float(current / target * Decimal(100))

    @property
    def remaining_amount(self) -> Decimal:
        """Amount still needed to hit target. Clamps at 0 — a goal
        the user has already overshot doesn't need ``-X``."""
        remaining = Decimal(self.target_amount or 0) - Decimal(
            self.current_amount or 0
        )
        return remaining if remaining > 0 else Decimal(0)

    @property
    def is_completed(self) -> bool:
        return self.status == "completed"
