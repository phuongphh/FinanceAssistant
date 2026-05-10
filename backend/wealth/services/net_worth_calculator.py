"""Net worth calculation — current, historical, and change-over-period.

Used by the morning briefing, the Mini App dashboard, and Phase 3B
investment intelligence. Performance critical (runs on every dashboard
load) so historical lookups use ``DISTINCT ON (asset_id)`` to avoid
N+1 queries.

All math goes through ``Decimal`` — money MUST NOT touch ``float`` per
CLAUDE.md § 13.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.wealth.models.asset import Asset
from backend.wealth.services import asset_service
from backend.wealth.valuation.crypto import value_crypto_holding
from backend.wealth.valuation.stock import value_stock_holding

PERIOD_DAY = "day"
PERIOD_WEEK = "week"
PERIOD_MONTH = "month"
PERIOD_YEAR = "year"

_PERIOD_DAYS = {
    PERIOD_DAY: 1,
    PERIOD_WEEK: 7,
    PERIOD_MONTH: 30,
    PERIOD_YEAR: 365,
}

_PERIOD_LABELS = {
    PERIOD_DAY: "hôm qua",
    PERIOD_WEEK: "tuần trước",
    PERIOD_MONTH: "tháng trước",
    PERIOD_YEAR: "năm trước",
}


@dataclass
class NetWorthBreakdown:
    """Snapshot of a user's net worth at a moment in time."""

    total: Decimal = Decimal(0)
    by_type: dict[str, Decimal] = field(default_factory=dict)
    asset_count: int = 0
    largest_asset: tuple[str | None, Decimal] = (None, Decimal(0))
    currency: str = "VND"


@dataclass
class NetWorthYtdReturn:
    """Year-to-date return using Jan-1 as the baseline when available."""

    current: Decimal
    base: Decimal
    change_absolute: Decimal
    change_percentage: float | None
    period_label: str
    is_join_date_fallback: bool = False


@dataclass
class NetWorthChange:
    """Change between two points (current vs ``period`` ago)."""

    current: Decimal
    previous: Decimal
    change_absolute: Decimal
    change_percentage: float
    period_label: str


async def calculate(db: AsyncSession, user_id: uuid.UUID) -> NetWorthBreakdown:
    """Sum every active asset's ``current_value`` and break down by type.

    Edge case: user with 0 assets returns an empty breakdown — never
    raises, never divides by zero.
    """
    assets: list[Asset] = await asset_service.get_user_assets(db, user_id)
    if not assets:
        return NetWorthBreakdown()

    by_type: dict[str, Decimal] = {}
    total = Decimal(0)
    largest_name: str | None = None
    largest_value = Decimal(0)

    for a in assets:
        if a.asset_type == "stock":
            valuation = await value_stock_holding(a)
            value = valuation.current_value
        elif a.asset_type == "crypto":
            valuation = await value_crypto_holding(a)
            value = valuation.current_value
        else:
            value = Decimal(a.current_value or 0)
        total += value
        by_type[a.asset_type] = by_type.get(a.asset_type, Decimal(0)) + value
        if value > largest_value:
            largest_value = value
            largest_name = a.name

    return NetWorthBreakdown(
        total=total,
        by_type=by_type,
        asset_count=len(assets),
        largest_asset=(largest_name, largest_value),
    )


async def calculate_stored_current(
    db: AsyncSession, user_id: uuid.UUID
) -> NetWorthBreakdown:
    """Sum active assets from stored ``current_value`` only.

    This intentionally skips live stock/crypto market valuation. Use it for
    deterministic UI surfaces (for example Telegram menu taps) where latency
    matters more than refreshing quotes on demand. Rich free-form queries and
    dashboards can still call :func:`calculate` when they want live pricing.
    """
    assets: list[Asset] = await asset_service.get_user_assets(db, user_id)
    if not assets:
        return NetWorthBreakdown()

    by_type: dict[str, Decimal] = {}
    total = Decimal(0)
    largest_name: str | None = None
    largest_value = Decimal(0)

    for a in assets:
        value = Decimal(a.current_value or 0)
        total += value
        by_type[a.asset_type] = by_type.get(a.asset_type, Decimal(0)) + value
        if value > largest_value:
            largest_value = value
            largest_name = a.name

    return NetWorthBreakdown(
        total=total,
        by_type=by_type,
        asset_count=len(assets),
        largest_asset=(largest_name, largest_value),
    )


async def calculate_historical(
    db: AsyncSession, user_id: uuid.UUID, target_date: date
) -> Decimal:
    """Net worth at end-of-day ``target_date``.

    Uses Postgres ``DISTINCT ON (asset_id)`` to pick the latest snapshot
    on or before the target date — one row per asset, single scan.
    Returns 0 if no snapshots exist on/before that date.
    """
    stmt = text(
        """
        SELECT COALESCE(SUM(value), 0) AS total FROM (
            SELECT DISTINCT ON (asset_id) value
            FROM asset_snapshots
            WHERE user_id = :user_id
              AND snapshot_date <= :target_date
            ORDER BY asset_id, snapshot_date DESC
        ) latest
        """
    ).bindparams(
        bindparam("user_id"),
        bindparam("target_date"),
    )
    result = await db.execute(stmt, {"user_id": user_id, "target_date": target_date})
    total = result.scalar() or Decimal(0)
    return Decimal(total)


async def calculate_change_from_current(
    db: AsyncSession,
    user_id: uuid.UUID,
    current: Decimal,
    period: str = PERIOD_DAY,
) -> NetWorthChange:
    """Compare a known current net worth to ``period`` ago.

    Use this when the caller already calculated the current breakdown.
    It avoids a second live asset valuation pass in hot paths such as
    ``query_net_worth`` while preserving the exact historical comparison
    semantics of :func:`calculate_change`.

    Edge cases:
    - User has no historical snapshots → previous=0, change=current
    - User had 0 net worth ``period`` ago → percentage stays 0 to avoid
      misleading "+inf%" UI.
    """
    if period not in _PERIOD_DAYS:
        raise ValueError(
            f"Unknown period {period!r}; must be one of {list(_PERIOD_DAYS)}"
        )

    current = Decimal(current or 0)
    past = date.today() - timedelta(days=_PERIOD_DAYS[period])
    previous = await calculate_historical(db, user_id, past)

    change_absolute = current - previous
    if previous > 0:
        change_pct = float(change_absolute / previous * 100)
    else:
        # No baseline — treat as flat rather than "infinite growth".
        change_pct = 0.0

    return NetWorthChange(
        current=current,
        previous=previous,
        change_absolute=change_absolute,
        change_percentage=change_pct,
        period_label=_PERIOD_LABELS[period],
    )


async def calculate_ytd_return_from_current(
    db: AsyncSession,
    user_id: uuid.UUID,
    current: Decimal,
    *,
    account_created_at: datetime | date | None = None,
    today: date | None = None,
) -> NetWorthYtdReturn:
    """Calculate true YTD return from Jan 1 of the current year.

    If the account was created after Jan 1, the label falls back to
    ``Từ ngày tham gia`` and the baseline date becomes the join date.
    A zero/missing baseline returns ``change_percentage=None`` so callers
    can render ``—`` instead of divide-by-zero or misleading infinity.
    """
    today = today or date.today()
    year_start = date(today.year, 1, 1)
    baseline_date = year_start
    is_join_date_fallback = False

    if account_created_at is not None:
        joined_date = (
            account_created_at.date()
            if isinstance(account_created_at, datetime)
            else account_created_at
        )
        if joined_date > year_start:
            baseline_date = joined_date
            is_join_date_fallback = True

    current = Decimal(current or 0)
    base = await calculate_historical(db, user_id, baseline_date)
    change_absolute = current - base
    change_pct: float | None
    if base > 0:
        change_pct = float(change_absolute / base * 100)
    else:
        change_pct = None

    return NetWorthYtdReturn(
        current=current,
        base=base,
        change_absolute=change_absolute,
        change_percentage=change_pct,
        period_label="Từ ngày tham gia" if is_join_date_fallback else "YTD",
        is_join_date_fallback=is_join_date_fallback,
    )


async def calculate_change(
    db: AsyncSession, user_id: uuid.UUID, period: str = PERIOD_DAY
) -> NetWorthChange:
    """Compare current net worth to ``period`` ago.

    This compatibility wrapper still computes the current breakdown for
    callers that only need a one-shot change result. Callers that already
    have a current total should use :func:`calculate_change_from_current`
    to avoid duplicate asset queries / live valuations.
    """
    current_breakdown = await calculate(db, user_id)
    return await calculate_change_from_current(
        db, user_id, current_breakdown.total, period=period
    )
