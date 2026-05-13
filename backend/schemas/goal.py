"""Pydantic schemas for ``Goal`` create / update / response + projection.

Phase 3.8 Epic 5 rewrite. Field renames vs Phase 3A:
- ``goal_name`` → ``name`` (matches spec § 2.2 + agent tool surface)
- ``deadline`` → ``target_date``
- ``priority``: str ("high"/"medium"/"low") → int 1-10 (1=highest);
  multi-goal ranking math (Phase 4) needs a sortable type
- ``is_active`` Bool → ``status`` enum string (active / completed /
  paused / abandoned) — distinguishes "user finished" from "user
  paused"

The ``GoalProjection`` payload is the agent / wizard format for
"feasibility" responses — see ``backend.services.goal_projection``
for the producer.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class GoalStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    PAUSED = "paused"
    ABANDONED = "abandoned"


class FeasibilityBand(str, Enum):
    """Spec § P3.8-S14 feasibility levels.

    Stable token (vs localised text) so the wizard / agent / future
    Mini App branches on band without parsing strings."""

    EASY = "easy"               # required ≤ 0.5× actual savings
    FEASIBLE = "feasible"       # 0.5-1.0× — current savings sufficient
    STRETCH = "stretch"         # 1.0-1.5× — need to step up
    AMBITIOUS = "ambitious"     # 1.5-2.0×
    NEEDS_REVISION = "needs_revision"  # >2× — unrealistic at current rate
    UNKNOWN = "unknown"         # can't compute (no saving-rate data)


class GoalCreate(BaseModel):
    """Wizard payload for adding a goal.

    ``template_id`` is optional — the wizard's "Tự tạo" path leaves
    it null. ``name`` is required either way (templates pre-fill it
    from YAML). ``target_date=None`` means open-ended; projection
    switches to "if you save X/month, you'll hit it in Y months"
    mode in that case."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    name: str = Field(..., min_length=1, max_length=500)
    target_amount: Decimal = Field(..., gt=0)
    current_amount: Decimal = Field(default=Decimal("0"), ge=0)
    target_date: Optional[date] = None
    template_id: Optional[str] = Field(default=None, max_length=50)
    icon: Optional[str] = Field(default=None, max_length=20)
    priority: int = Field(default=5, ge=1, le=10)


class GoalUpdate(BaseModel):
    """Partial update — only fields explicitly set are touched."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    name: Optional[str] = Field(default=None, min_length=1, max_length=500)
    target_amount: Optional[Decimal] = Field(default=None, gt=0)
    target_date: Optional[date] = None
    priority: Optional[int] = Field(default=None, ge=1, le=10)
    status: Optional[GoalStatus] = None
    icon: Optional[str] = None
    monthly_savings_required: Optional[Decimal] = None


class GoalProgressUpdate(BaseModel):
    """Payload for the "update progress" sub-wizard. ``current_amount``
    is the total to-date, not a delta — matches user mental model
    ("tôi đã có 200tr") better than "+50tr"."""

    model_config = ConfigDict(extra="forbid")

    current_amount: Decimal = Field(..., ge=0)


class GoalResponse(BaseModel):
    """Read-only payload returned by REST + agent tool."""

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    template_id: Optional[str] = None
    icon: Optional[str] = None
    target_amount: Decimal
    current_amount: Decimal
    target_date: Optional[date] = None
    monthly_savings_required: Optional[Decimal] = None
    status: str
    priority: int
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None


class GoalProjection(BaseModel):
    """Output of ``GoalProjectionService.project_goal``.

    Carries either ``required_monthly_savings`` + ``feasibility``
    (when ``target_date`` is set) OR ``estimated_completion_*``
    (when open-ended). Never both — readers branch on which fields
    are present.
    """

    model_config = ConfigDict(use_enum_values=True)

    goal_id: uuid.UUID
    remaining_amount: Decimal
    current_progress_pct: float

    # Set when target_date is known.
    months_remaining: Optional[int] = None
    required_monthly_savings: Optional[Decimal] = None
    feasibility: Optional[FeasibilityBand] = None
    avg_monthly_savings: Optional[Decimal] = None

    # Set when target_date is open-ended AND user has positive avg
    # savings. Both null = "open-ended but no saving-rate data".
    estimated_completion_months: Optional[float] = None
    estimated_completion_date: Optional[date] = None

    # Always populated — supportive framing for wizard.
    notes: list[str] = Field(default_factory=list)


class IncomeUpdate(BaseModel):
    """Legacy ``users.monthly_income`` setter. Kept here for the
    REST router that pre-dates the IncomeStream wizard."""

    monthly_income: float = Field(..., gt=0)


__all__ = [
    "FeasibilityBand",
    "GoalCreate",
    "GoalProgressUpdate",
    "GoalProjection",
    "GoalResponse",
    "GoalStatus",
    "GoalUpdate",
    "IncomeUpdate",
]
