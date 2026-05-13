"""Cashflow forecasting + runway analysis — Phase 3.8 Epic 4.

Simple v1 methodology (per spec § 2.1):

For each future month M:
  expected_income(M)   = sum of income streams firing in M
  expected_expense(M)  = sum of recurring patterns + ambient_avg
  expected_savings(M)  = income − expense
  confidence(M)        = max(0.30, 1.00 − month_offset × 0.15)

Why we don't naively use ``avg(last 3 months income/expense)``:
that would double-count salary streams (they're already in last
3 months *and* in the streams table). Instead we:

- Drive INCOME entirely from streams. Each stream contributes in
  the months its schedule fires (monthly = every month, quarterly =
  every 3rd, annually = once on ``schedule_month``, ad_hoc = smoothed
  via ``monthly_equivalent``).
- Drive EXPENSE from (recurring patterns) + (ambient baseline).
  Ambient = avg over last 3 months of expenses NOT linked to a
  recurrence_id. Cleanly separates "committed" from "discretionary".

Edge cases the function handles explicitly:
- 0 income streams → expected_income = 0, ``notes`` warns
- 0 expense history → ambient = 0, ``notes`` warns
- <3 months of expense data → use whatever we have, ``confidence``
  carries an extra 0.7× multiplier flagged in notes

``RunwayAnalyzer`` answers "if income stops today, how many months
can I survive?". Liquid assets = ``cash`` asset_type (any subtype).
Stocks / BĐS / crypto / gold are illiquid and excluded — selling
those takes time and triggers tax events; they shouldn't count as
runway buffer.

Layer contract: pure read; never flushes; never calls Telegram /
LLM. Caller passes an open ``AsyncSession``.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.expense import Expense
from backend.models.recurring_pattern import RecurringPattern
from backend.models.user import User
from backend.schemas.cashflow import MonthlyForecast, RunwayResult
from backend.wealth.models.asset import Asset
from backend.wealth.models.income_stream import IncomeStream


# Constants — match spec § 2.1.
BASELINE_MONTHS = 3
LOW_DATA_CONFIDENCE_MULTIPLIER = 0.7
CONFIDENCE_FLOOR = 0.30
CONFIDENCE_DECAY_PER_MONTH = 0.15
CONFIDENCE_MONTH_1 = 1.00 - CONFIDENCE_DECAY_PER_MONTH  # 0.85

RUNWAY_CRITICAL_MONTHS = 3
RUNWAY_TIGHT_MONTHS = 6

# Lifestyle = discretionary. Excluded from "essential expenses" for
# the runway calculation per spec § 2.1.
LIFESTYLE_CATEGORIES = frozenset(
    {"entertainment", "shopping", "gift"}
)


# ---------------------------------------------------------------------
# Public API — CashflowForecaster
# ---------------------------------------------------------------------


async def forecast(
    db: AsyncSession,
    user_id,
    *,
    months_ahead: int = 3,
    today: date | None = None,
) -> list[MonthlyForecast]:
    """Project ``months_ahead`` months of income / expense / savings.

    See module docstring for methodology. Returns empty list when
    ``months_ahead <= 0`` rather than throwing — keeps the agent
    tool's input validation simpler.
    """
    if months_ahead <= 0:
        return []
    today = today or date.today()

    streams = await _load_active_income_streams(db, user_id)
    patterns = await _load_active_recurring_patterns(db, user_id)
    ambient_expense, has_low_data = await _compute_ambient_monthly_expense(
        db, user_id, today=today,
    )

    notes_global: list[str] = []
    if not streams:
        notes_global.append("Chưa có nguồn thu nhập — chỉ dự báo chi tiêu.")
    if has_low_data:
        notes_global.append("Dữ liệu chi tiêu <3 tháng — tin cậy giảm.")

    forecasts: list[MonthlyForecast] = []
    for offset in range(1, months_ahead + 1):
        month_first = _first_of_month_offset(today, offset)
        income = _income_for_month(streams, month_first)
        recurring = _recurring_expense_for_month(patterns, month_first)
        expense = recurring + ambient_expense
        savings = income - expense

        confidence = _confidence(offset)
        if has_low_data:
            confidence = max(
                CONFIDENCE_FLOOR,
                confidence * LOW_DATA_CONFIDENCE_MULTIPLIER,
            )

        notes = list(notes_global)
        if savings < 0:
            notes.append(
                f"Tháng {month_first.month}/{month_first.year}: "
                "dự kiến âm — chi vượt thu."
            )

        forecasts.append(MonthlyForecast(
            month=month_first,
            expected_income=income,
            expected_expense=expense,
            expected_savings=savings,
            confidence=round(confidence, 2),
            breakdown={
                "scheduled_income": income,
                "recurring_expense": recurring,
                "ambient_expense": ambient_expense,
            },
            notes=notes,
        ))
    return forecasts


# ---------------------------------------------------------------------
# Public API — RunwayAnalyzer
# ---------------------------------------------------------------------


async def compute_runway(
    db: AsyncSession,
    user_id,
    *,
    today: date | None = None,
) -> RunwayResult:
    """How long can the user survive on liquid assets if income stops?

    ``months = liquid_assets / monthly_burn``. ``None`` for months
    means "no essential burn detected" — we explicitly *don't*
    return ``inf`` because consumers (Mini App, agent formatter)
    would have to special-case it; ``None`` is the standard "no
    answer" sentinel and forces them to.
    """
    today = today or date.today()
    liquid = await _liquid_assets(db, user_id)
    burn = await _essential_monthly_expense(db, user_id, today=today)

    if burn <= 0:
        return RunwayResult(
            months=None,
            liquid_assets=liquid,
            monthly_burn=Decimal(0),
            warning=None,
            band="unknown",
        )

    months = float(liquid / burn) if burn > 0 else None
    warning, band = _runway_warning_band(months)
    return RunwayResult(
        months=months,
        liquid_assets=liquid,
        monthly_burn=burn,
        warning=warning,
        band=band,
    )


# ---------------------------------------------------------------------
# Internals — schedule arithmetic
# ---------------------------------------------------------------------


def _confidence(month_offset: int) -> float:
    """Spec formula: max(0.30, 1.0 − offset × 0.15).

    offset=1 → 0.85, offset=2 → 0.70, offset=3 → 0.55, offset≥5 → 0.30.
    """
    return max(CONFIDENCE_FLOOR, 1.0 - month_offset * CONFIDENCE_DECAY_PER_MONTH)


def _first_of_month_offset(today: date, offset: int) -> date:
    """Return the first day of the month ``offset`` months after
    ``today``. Handles year wrap (Dec + 1 = next Jan)."""
    month = today.month + offset
    year = today.year
    while month > 12:
        month -= 12
        year += 1
    return date(year, month, 1)


def _income_for_month(
    streams: list[IncomeStream], month_first: date,
) -> Decimal:
    """Sum stream contributions for the calendar month containing
    ``month_first``.

    Per-schedule rules:
    - monthly: contributes ``amount`` every month
    - quarterly: contributes ``amount`` every 3rd month from
      ``schedule_month`` (e.g. mar/jun/sep/dec for schedule_month=3)
    - annually: contributes ``amount`` only in ``schedule_month``
      (12/December if not set — VN year-end dividend default)
    - ad_hoc: contributes ``monthly_equivalent`` (smoothed) — we
      have no firing schedule for these
    """
    total = Decimal(0)
    target = month_first.month
    for s in streams:
        # Skip streams that ended before this forecast month.
        if s.end_date is not None and s.end_date < month_first:
            continue
        # Skip streams that haven't started yet — common when user
        # adds "freelance starting next month".
        if s.start_date is not None and s.start_date > _last_of_month(month_first):
            continue
        sched = s.schedule_type
        amount = Decimal(s.amount or 0)
        if sched == "monthly":
            total += amount
        elif sched == "quarterly":
            anchor = s.schedule_month or month_first.month
            if (target - anchor) % 3 == 0:
                total += amount
        elif sched == "annually":
            anchor = s.schedule_month or 12
            if target == anchor:
                total += amount
        else:
            # ad_hoc / unknown — contribute the smoothed monthly
            # equivalent. Better than zero (which would underforecast)
            # and better than full amount (which would overforecast).
            total += s.monthly_equivalent
    return total


def _recurring_expense_for_month(
    patterns: list[RecurringPattern], month_first: date,
) -> Decimal:
    """Sum recurring patterns that fire in this month.

    Phase 3.8 only ships ``schedule_type='monthly'``, so each active
    pattern contributes once per month. Future quarterly/annually
    patterns can be handled here mirroring the income logic."""
    total = Decimal(0)
    for p in patterns:
        if not p.is_active:
            continue
        if p.schedule_type == "monthly":
            total += Decimal(p.expected_amount)
        # Other schedules: contribute when their day fires this
        # month. Day-of-month doesn't change "does it fire this
        # month?", so the answer for monthly is "yes always".
    return total


def _last_of_month(month_first: date) -> date:
    last_dom = calendar.monthrange(month_first.year, month_first.month)[1]
    return date(month_first.year, month_first.month, last_dom)


# ---------------------------------------------------------------------
# Internals — DB readers
# ---------------------------------------------------------------------


async def _load_active_income_streams(
    db: AsyncSession, user_id,
) -> list[IncomeStream]:
    stmt = select(IncomeStream).where(
        and_(
            IncomeStream.user_id == user_id,
            IncomeStream.is_active.is_(True),
        )
    )
    return list((await db.execute(stmt)).scalars().all())


async def _load_active_recurring_patterns(
    db: AsyncSession, user_id,
) -> list[RecurringPattern]:
    stmt = select(RecurringPattern).where(
        and_(
            RecurringPattern.user_id == user_id,
            RecurringPattern.is_active.is_(True),
        )
    )
    return list((await db.execute(stmt)).scalars().all())


async def _compute_ambient_monthly_expense(
    db: AsyncSession, user_id, *, today: date,
) -> tuple[Decimal, bool]:
    """Average monthly expense for transactions NOT linked to a
    recurring pattern.

    Why "not linked": recurring patterns are added separately via
    ``_recurring_expense_for_month``. If we included them here too,
    the user's salary on the 5th would forecast as 2× monthly rent.

    Returns ``(ambient_per_month, has_low_data)``. ``has_low_data``
    is True when we found <3 distinct months — the caller drops
    confidence accordingly.
    """
    since = date(today.year, today.month, 1) - timedelta(days=BASELINE_MONTHS * 31)
    stmt = select(Expense).where(
        Expense.user_id == user_id,
        Expense.expense_date >= since,
        Expense.expense_date < date(today.year, today.month, 1),
        Expense.deleted_at.is_(None),
        Expense.transaction_type == "expense",
        Expense.recurrence_id.is_(None),
    )
    rows = list((await db.execute(stmt)).scalars().all())
    if not rows:
        return Decimal(0), True

    distinct_months = {(e.expense_date.year, e.expense_date.month) for e in rows}
    months = max(len(distinct_months), 1)
    total = sum((Decimal(e.amount or 0) for e in rows), Decimal(0))
    ambient = (total / Decimal(months)).quantize(Decimal("1"))
    return ambient, months < BASELINE_MONTHS


async def _liquid_assets(db: AsyncSession, user_id) -> Decimal:
    """Cash assets — bank savings/checking, physical cash, e-wallet.

    Stocks / BĐS / crypto / gold are excluded: selling takes days
    (best case), triggers tax/fees, and the user can't realistically
    cover next month's rent with them. Bonds are illiquid in VN
    retail context (5-year terms typical) so also excluded.
    """
    stmt = select(Asset).where(
        Asset.user_id == user_id,
        Asset.asset_type == "cash",
        Asset.is_active.is_(True),
    )
    rows = (await db.execute(stmt)).scalars().all()
    return sum((Decimal(a.current_value or 0) for a in rows), Decimal(0))


async def _essential_monthly_expense(
    db: AsyncSession, user_id, *, today: date,
) -> Decimal:
    """Recurring patterns + ambient (excluding lifestyle) per month.

    Lifestyle excluded because runway = "what I MUST cover" not
    "what I would cover". Restaurant / shopping / gift can pause
    when income stops; rent and electricity can't.
    """
    patterns = await _load_active_recurring_patterns(db, user_id)
    recurring_essential = sum(
        (Decimal(p.expected_amount) for p in patterns if p.is_active),
        Decimal(0),
    )
    ambient_essential = await _compute_ambient_essential(
        db, user_id, today=today,
    )
    return recurring_essential + ambient_essential


async def _compute_ambient_essential(
    db: AsyncSession, user_id, *, today: date,
) -> Decimal:
    """Average over last 3 months of NON-recurring NON-lifestyle
    expenses. The "must-cover" portion of discretionary spend
    (groceries are 'food' = non-lifestyle but also non-recurring)."""
    since = date(today.year, today.month, 1) - timedelta(days=BASELINE_MONTHS * 31)
    stmt = select(Expense).where(
        Expense.user_id == user_id,
        Expense.expense_date >= since,
        Expense.expense_date < date(today.year, today.month, 1),
        Expense.deleted_at.is_(None),
        Expense.transaction_type == "expense",
        Expense.recurrence_id.is_(None),
        Expense.category.notin_(LIFESTYLE_CATEGORIES),
    )
    rows = list((await db.execute(stmt)).scalars().all())
    if not rows:
        return Decimal(0)
    distinct_months = {(e.expense_date.year, e.expense_date.month) for e in rows}
    months = max(len(distinct_months), 1)
    total = sum((Decimal(e.amount or 0) for e in rows), Decimal(0))
    return (total / Decimal(months)).quantize(Decimal("1"))


def _runway_warning_band(months: float | None) -> tuple[str | None, str]:
    """Map a runway figure to a (warning, band) pair.

    Spec § 2.1 thresholds:
    - <3 months: 🚨 — emergency-fund gap
    - 3-6: ⚠️ — okay but build buffer
    - >6: no warning, comfortable band
    """
    if months is None:
        return None, "unknown"
    if months < RUNWAY_CRITICAL_MONTHS:
        return (
            "🚨 Runway dưới 3 tháng — nên build emergency fund.",
            "critical",
        )
    if months < RUNWAY_TIGHT_MONTHS:
        return (
            "⚠️ Runway 3-6 tháng — okay nhưng có thể tốt hơn.",
            "tight",
        )
    return None, "comfortable"
