"""Phase 4B S16 — 3-month cashflow forecast model.

Builds on the Phase 3.8 ``cashflow_forecaster`` by:
- Using only **confirmed** recurring patterns (user_confirmed=True)
- Adjusting month-0 for actuals already recorded in the current month
- Persisting a ``CashflowForecast`` snapshot for the morning briefing
  and Mini App to read without re-computing
- Computing the low-balance threshold automatically when the user
  hasn't set one manually

Methodology:
    for each month M in [0, horizon_months):
        income_M  = sum(income-type patterns firing in M)
        expense_M = sum(expense-type patterns firing in M)
        if M == 0 (current month):
            income_M  -= already-recorded income YTM
            expense_M -= already-recorded expense YTM
        net_M         = income_M - expense_M
        balance_eom_M = running_balance + net_M

    low_balance_risk = any(balance_eom_M < threshold for M in months)

Layer contract: service flushes — caller commits.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any
import uuid

from dateutil.relativedelta import relativedelta
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.cashflow.detector import load_confirmed_patterns
from backend.models.cashflow_forecast import CashflowForecast, ENGINE_VERSION
from backend.models.expense import Expense
from backend.models.recurring_pattern import PATTERN_TYPE_INCOME, RecurringPattern
from backend.models.user import User
from backend.wealth.models.asset import Asset

logger = logging.getLogger(__name__)

# How long (in calendar days) before today to look for current-month actuals.
CURRENT_MONTH_LOOKBACK_BUFFER = 1   # start from first of month


@dataclass
class MonthlyForecastData:
    month: date           # first day of the month
    income: Decimal
    expense: Decimal
    net: Decimal
    balance_eom: Decimal  # balance at end of month

    def to_dict(self) -> dict[str, Any]:
        return {
            "month": self.month.isoformat(),
            "income": str(self.income),
            "expense": str(self.expense),
            "net": str(self.net),
            "balance_eom": str(self.balance_eom),
        }


# ── Public API ───────────────────────────────────────────────────────────────


async def compute_and_persist_forecast(
    db: AsyncSession,
    user: User,
    *,
    horizon_months: int = 3,
    today: date | None = None,
) -> CashflowForecast:
    """Compute the 3-month cashflow forecast and persist it.

    Returns the upserted ``CashflowForecast`` row (flushed, not
    committed — caller commits with the surrounding session).

    Raises ``ValueError`` if the user has fewer than 2 confirmed patterns
    (forecast would be unreliable — callers should skip/log and move on).
    """
    today = today or date.today()
    confirmed = await load_confirmed_patterns(db, user.id)

    if len(confirmed) < 2:
        raise ValueError(
            f"user {user.id}: fewer than 2 confirmed patterns — skipping forecast"
        )

    current_balance = await _get_current_balance(db, user.id)
    current_month_actuals = await _get_current_month_actuals(db, user.id, today)
    threshold = _compute_threshold(user, confirmed)

    monthly_data: list[MonthlyForecastData] = []
    running_balance = current_balance

    for offset in range(horizon_months):
        target_month = _month_start_offset(today, offset)
        proj_income = _sum_patterns(confirmed, PATTERN_TYPE_INCOME, target_month)
        proj_expense = _sum_patterns(confirmed, "expense", target_month)

        if offset == 0:
            # Reduce projected by actuals already recorded this month.
            actual_income = current_month_actuals.get("income", Decimal(0))
            actual_expense = current_month_actuals.get("expense", Decimal(0))
            proj_income = max(Decimal(0), proj_income - actual_income)
            proj_expense = max(Decimal(0), proj_expense - actual_expense)

        net = proj_income - proj_expense
        running_balance += net

        monthly_data.append(MonthlyForecastData(
            month=target_month,
            income=proj_income.quantize(Decimal("0.01")),
            expense=proj_expense.quantize(Decimal("0.01")),
            net=net.quantize(Decimal("0.01")),
            balance_eom=running_balance.quantize(Decimal("0.01")),
        ))

    low_balance_months = [m for m in monthly_data if m.balance_eom < threshold]
    low_balance_risk = bool(low_balance_months)
    low_balance_month = (
        min(low_balance_months, key=lambda m: m.month).month
        if low_balance_months else None
    )

    row = await _upsert_forecast(
        db,
        user_id=user.id,
        forecast_date=today,
        horizon_months=horizon_months,
        monthly_data=[m.to_dict() for m in monthly_data],
        low_balance_risk=low_balance_risk,
        low_balance_month=low_balance_month,
        low_balance_threshold=threshold,
    )
    logger.info(
        "cashflow forecast: user=%s date=%s patterns=%d low_risk=%s",
        user.id, today, len(confirmed), low_balance_risk,
    )
    return row


async def get_latest_forecast(
    db: AsyncSession, user_id: uuid.UUID,
) -> CashflowForecast | None:
    """Return the most recent forecast row for the user, or None."""
    stmt = (
        select(CashflowForecast)
        .where(CashflowForecast.user_id == user_id)
        .order_by(CashflowForecast.forecast_date.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalars().first()


# ── Internals ────────────────────────────────────────────────────────────────


def _sum_patterns(
    patterns: list[RecurringPattern],
    pattern_type: str,
    month_first: date,
) -> Decimal:
    """Sum patterns of a given type that fire in ``month_first``'s month.

    Currently only 'monthly' schedule supported — each pattern contributes
    once per month regardless of day-of-month.
    """
    total = Decimal(0)
    for p in patterns:
        if p.pattern_type != pattern_type:
            continue
        if not p.is_active:
            continue
        if p.schedule_type == "monthly":
            total += Decimal(str(p.expected_amount))
    return total


def _compute_threshold(user: User, patterns: list[RecurringPattern]) -> Decimal:
    """User threshold or fallback = avg monthly expense from confirmed patterns."""
    if user.cashflow_alert_threshold is not None:
        return Decimal(str(user.cashflow_alert_threshold))
    expense_total = sum(
        Decimal(str(p.expected_amount))
        for p in patterns
        if p.pattern_type == "expense"
    )
    return expense_total  # 1× monthly expense


async def _get_current_balance(db: AsyncSession, user_id: uuid.UUID) -> Decimal:
    """Sum of liquid cash assets (asset_type='cash')."""
    stmt = select(Asset).where(
        and_(
            Asset.user_id == user_id,
            Asset.asset_type == "cash",
            Asset.is_active.is_(True),
        )
    )
    rows = (await db.execute(stmt)).scalars().all()
    return sum((Decimal(str(a.current_value or 0)) for a in rows), Decimal(0))


async def _get_current_month_actuals(
    db: AsyncSession,
    user_id: uuid.UUID,
    today: date,
) -> dict[str, Decimal]:
    """Sum income and expense already recorded in the current calendar month."""
    month_start = today.replace(day=1)

    # Expenses this month
    stmt = select(Expense).where(
        and_(
            Expense.user_id == user_id,
            Expense.expense_date >= month_start,
            Expense.expense_date <= today,
            Expense.deleted_at.is_(None),
        )
    )
    expenses = (await db.execute(stmt)).scalars().all()
    expense_total = sum(
        (Decimal(str(e.amount or 0)) for e in expenses), Decimal(0)
    )

    # Income records this month (best-effort — may not exist in all deployments)
    income_total = Decimal(0)
    try:
        from backend.models.income_record import IncomeRecord
        istmt = select(IncomeRecord).where(
            and_(
                IncomeRecord.user_id == user_id,
                IncomeRecord.period >= month_start,
                IncomeRecord.period <= today,
            )
        )
        irecs = (await db.execute(istmt)).scalars().all()
        income_total = sum(
            (Decimal(str(r.amount or 0)) for r in irecs), Decimal(0)
        )
    except Exception:
        pass

    return {"income": income_total, "expense": expense_total}


async def _upsert_forecast(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    forecast_date: date,
    horizon_months: int,
    monthly_data: list[dict],
    low_balance_risk: bool,
    low_balance_month: date | None,
    low_balance_threshold: Decimal,
) -> CashflowForecast:
    """Insert or replace today's forecast for the user.

    Uses a delete-then-insert approach (simpler than ON CONFLICT with
    JSONB update) since the daily cron is the sole writer.
    """
    stmt = select(CashflowForecast).where(
        and_(
            CashflowForecast.user_id == user_id,
            CashflowForecast.forecast_date == forecast_date,
        )
    )
    existing = (await db.execute(stmt)).scalars().first()
    if existing is not None:
        await db.delete(existing)
        await db.flush()

    row = CashflowForecast(
        user_id=user_id,
        forecast_date=forecast_date,
        computed_at=datetime.utcnow(),
        horizon_months=horizon_months,
        monthly_data=monthly_data,
        low_balance_risk=low_balance_risk,
        low_balance_month=low_balance_month,
        low_balance_threshold=low_balance_threshold,
        engine_version=ENGINE_VERSION,
    )
    db.add(row)
    await db.flush()
    return row


def _month_start_offset(today: date, offset: int) -> date:
    """First day of the month ``offset`` months from ``today``."""
    return (today.replace(day=1) + relativedelta(months=offset))
