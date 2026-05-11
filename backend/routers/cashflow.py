"""FastAPI routes for Cashflow Forecasting v2 (Phase 4B Epic 3, S20).

Surfaces:
- Mini App "Dòng tiền" tab: read forecast, list/create/update patterns
- Telegram settings: /settings cashflow_threshold <amount>

Auth: Telegram WebApp initData via ``require_miniapp_auth``.
User scoping enforced in all service calls.

Layer contract:
- Routes parse HTTP, call services, return responses.
- No business logic, no db.commit() — session committed by FastAPI lifespan.
- Decimal coerced to str in responses (JSON-safe, no float drift).
"""
from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.cashflow.detector import (
    load_confirmed_patterns,
    load_unconfirmed_pending,
)
from backend.cashflow.forecast import (
    compute_and_persist_forecast,
    get_latest_forecast,
)
from backend.database import get_db
from backend.miniapp.auth import require_miniapp_auth
from backend.miniapp.routes import _resolve_user
from backend.models.cashflow_forecast import CashflowForecast
from backend.models.recurring_pattern import RecurringPattern

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cashflow", tags=["cashflow"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────


class PatternRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    pattern_type: str
    name: str
    description: Optional[str]
    expected_amount: Decimal
    typical_day: Optional[int] = Field(None, alias="expected_day_of_month")
    confidence: Optional[Decimal]
    is_confirmed: bool = Field(False, alias="user_confirmed")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class PatternUpdate(BaseModel):
    expected_amount: Optional[Decimal] = None
    expected_day_of_month: Optional[int] = None


class PatternCreate(BaseModel):
    pattern_type: str = "expense"
    name: str = Field(..., min_length=1, max_length=200)
    expected_amount: Decimal = Field(..., gt=0)
    expected_day_of_month: Optional[int] = Field(None, ge=1, le=31)


class ForecastRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    forecast_date: str
    horizon_months: int
    monthly_data: list[dict]
    low_balance_risk: bool
    low_balance_month: Optional[str]
    low_balance_threshold: Optional[Decimal]


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/forecast", response_model=ForecastRead)
async def get_cashflow_forecast(
    auth: dict = Depends(require_miniapp_auth),
    db: AsyncSession = Depends(get_db),
):
    """Return the latest 3-month cashflow forecast for the authenticated user."""
    user = await _resolve_user(auth, db)
    forecast = await get_latest_forecast(db, user.id)
    if forecast is None:
        raise HTTPException(status_code=404, detail="Chưa có dự báo cashflow.")
    return _serialize_forecast(forecast)


@router.post("/forecast/refresh", response_model=ForecastRead)
async def refresh_cashflow_forecast(
    auth: dict = Depends(require_miniapp_auth),
    db: AsyncSession = Depends(get_db),
):
    """Trigger an immediate forecast recompute (on-demand, max once per day)."""
    user = await _resolve_user(auth, db)
    try:
        forecast = await compute_and_persist_forecast(db, user)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _serialize_forecast(forecast)


@router.get("/patterns", response_model=list[PatternRead])
async def get_patterns(
    include_unconfirmed: bool = Query(False),
    auth: dict = Depends(require_miniapp_auth),
    db: AsyncSession = Depends(get_db),
):
    """List confirmed (and optionally pending) recurring patterns."""
    user = await _resolve_user(auth, db)
    confirmed = await load_confirmed_patterns(db, user.id)
    if include_unconfirmed:
        pending = await load_unconfirmed_pending(db, user.id)
        return [_serialize_pattern(p) for p in confirmed + pending]
    return [_serialize_pattern(p) for p in confirmed]


@router.post("/patterns", response_model=PatternRead, status_code=201)
async def add_manual_pattern(
    payload: PatternCreate,
    auth: dict = Depends(require_miniapp_auth),
    db: AsyncSession = Depends(get_db),
):
    """Add a manually-entered recurring pattern (auto-confirmed)."""
    user = await _resolve_user(auth, db)
    pattern = RecurringPattern(
        user_id=user.id,
        name=payload.name,
        description=payload.name,
        category="manual",
        pattern_type=payload.pattern_type,
        expected_amount=payload.expected_amount,
        expected_day_of_month=payload.expected_day_of_month,
        schedule_type="monthly",
        is_active=True,
        auto_detected=False,
        user_confirmed=True,   # manual entries are pre-confirmed
        enable_reminders=True,
    )
    db.add(pattern)
    await db.flush()
    await db.commit()
    return _serialize_pattern(pattern)


@router.patch("/patterns/{pattern_id}", response_model=PatternRead)
async def update_pattern(
    pattern_id: uuid.UUID = Path(...),
    payload: PatternUpdate = ...,
    auth: dict = Depends(require_miniapp_auth),
    db: AsyncSession = Depends(get_db),
):
    """Update amount or day-of-month for an existing pattern."""
    user = await _resolve_user(auth, db)
    pattern = await _load_pattern_for_user(db, pattern_id, user.id)
    if pattern is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy khoản định kỳ.")

    if payload.expected_amount is not None:
        pattern.expected_amount = payload.expected_amount
    if payload.expected_day_of_month is not None:
        pattern.expected_day_of_month = payload.expected_day_of_month

    db.add(pattern)
    await db.flush()
    await db.commit()
    return _serialize_pattern(pattern)


@router.delete("/patterns/{pattern_id}", status_code=204)
async def delete_pattern(
    pattern_id: uuid.UUID = Path(...),
    auth: dict = Depends(require_miniapp_auth),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete a recurring pattern."""
    user = await _resolve_user(auth, db)
    pattern = await _load_pattern_for_user(db, pattern_id, user.id)
    if pattern is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy khoản định kỳ.")
    pattern.is_active = False
    db.add(pattern)
    await db.flush()
    await db.commit()


# ── Helpers ──────────────────────────────────────────────────────────────────


def _serialize_pattern(p: RecurringPattern) -> dict:
    return {
        "id": p.id,
        "pattern_type": p.pattern_type,
        "name": p.name,
        "description": p.description,
        "expected_amount": p.expected_amount,
        "typical_day": p.expected_day_of_month,
        "confidence": p.confidence,
        "is_confirmed": p.user_confirmed,
    }


def _serialize_forecast(f: CashflowForecast) -> dict:
    return {
        "forecast_date": f.forecast_date.isoformat() if f.forecast_date else None,
        "horizon_months": f.horizon_months,
        "monthly_data": f.monthly_data,
        "low_balance_risk": f.low_balance_risk,
        "low_balance_month": (
            f.low_balance_month.isoformat() if f.low_balance_month else None
        ),
        "low_balance_threshold": f.low_balance_threshold,
    }


async def _load_pattern_for_user(
    db: AsyncSession, pattern_id: uuid.UUID, user_id: uuid.UUID,
) -> RecurringPattern | None:
    from sqlalchemy import and_, select
    stmt = select(RecurringPattern).where(
        and_(
            RecurringPattern.id == pattern_id,
            RecurringPattern.user_id == user_id,
            RecurringPattern.is_active.is_(True),
        )
    )
    return (await db.execute(stmt)).scalars().first()
