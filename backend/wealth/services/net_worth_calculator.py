"""Net worth calculation — current, historical, and change-over-period.

Used by the morning briefing, the Mini App dashboard, and Phase 3B
investment intelligence. Performance critical (runs on every dashboard
load) so historical lookups use ``DISTINCT ON (asset_id)`` to avoid
N+1 queries.

All math goes through ``Decimal`` — money MUST NOT touch ``float`` per
CLAUDE.md § 13.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.wealth.models.asset import Asset
from backend.wealth.services import asset_service
from backend.wealth.valuation.crypto import (
    value_crypto_holding,
    value_crypto_holdings,
)
from backend.wealth.valuation.stock import (
    value_stock_holding,
    value_stock_holdings,
)

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

    Stock and crypto holdings are live-quoted. We fan the two asset
    classes out via batched provider calls (``value_stock_holdings`` /
    ``value_crypto_holdings``) and run the two classes in parallel —
    they hit different providers (stock dispatcher vs CoinGecko), so
    a portfolio with N stocks + M coins costs ``max(stock_call, crypto_call)``
    rather than the N+M sequential awaits this function used to issue.
    Cache hits stay cheap; the difference is dramatic on cold caches
    where each missing per-symbol HTTP request was a multi-second tail.

    Edge case: user with 0 assets returns an empty breakdown — never
    raises, never divides by zero.
    """
    assets: list[Asset] = await asset_service.get_user_assets(db, user_id)
    if not assets:
        return NetWorthBreakdown()

    stock_valuations, crypto_valuations = await asyncio.gather(
        value_stock_holdings(assets),
        value_crypto_holdings(assets),
    )

    by_type: dict[str, Decimal] = {}
    total = Decimal(0)
    largest_name: str | None = None
    largest_value = Decimal(0)

    for a in assets:
        if a.asset_type == "stock":
            valuation = stock_valuations.get(a)
            value = (
                valuation.current_value
                if valuation is not None
                else Decimal(a.current_value or 0)
            )
        elif a.asset_type == "crypto":
            valuation = crypto_valuations.get(a)
            value = (
                valuation.current_value
                if valuation is not None
                else Decimal(a.current_value or 0)
            )
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


@dataclass
class AssetMover:
    """One asset's day-over-day movement.

    ``previous_value`` is yesterday's ``asset_snapshots.value``; for
    new assets without yesterday data we omit the row rather than
    misrepresent a 100% gain.
    """
    asset_id: uuid.UUID
    name: str
    asset_type: str
    current_value: Decimal
    previous_value: Decimal
    change_absolute: Decimal
    change_percentage: float


async def get_daily_movers(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    today: date | None = None,
    min_abs_pct: float = 0.1,
) -> list[AssetMover]:
    """Return active assets whose value moved since yesterday.

    Each row joins the asset to its latest ``asset_snapshots`` value on
    or before ``today - 1``. Assets with no prior snapshot (just
    added) or whose absolute % change is below ``min_abs_pct`` are
    filtered out — neither is interesting on a "what moved today"
    list, and the new-asset case would otherwise read as "+100% so
    với hôm qua" which is misleading.

    Sorted by absolute % movement descending so the biggest swing
    leads, regardless of direction.
    """
    today = today or date.today()
    yesterday = today - timedelta(days=1)

    stmt = text(
        """
        SELECT
            a.id          AS asset_id,
            a.name        AS name,
            a.asset_type  AS asset_type,
            a.current_value AS current_value,
            (
                SELECT s.value
                FROM asset_snapshots s
                WHERE s.asset_id = a.id
                  AND s.snapshot_date <= :yesterday
                ORDER BY s.snapshot_date DESC
                LIMIT 1
            ) AS previous_value
        FROM assets a
        WHERE a.user_id = :user_id
          AND a.is_active = TRUE
        """
    ).bindparams(
        bindparam("user_id"),
        bindparam("yesterday"),
    )
    rows = (
        await db.execute(stmt, {"user_id": user_id, "yesterday": yesterday})
    ).mappings().all()

    movers: list[AssetMover] = []
    for row in rows:
        prev = row["previous_value"]
        curr = row["current_value"]
        if prev is None or curr is None:
            continue
        prev_d = Decimal(prev)
        curr_d = Decimal(curr)
        if prev_d <= 0:
            continue
        change_abs = curr_d - prev_d
        change_pct = float(change_abs / prev_d * Decimal(100))
        if abs(change_pct) < min_abs_pct:
            continue
        movers.append(
            AssetMover(
                asset_id=row["asset_id"],
                name=row["name"] or "",
                asset_type=row["asset_type"],
                current_value=curr_d,
                previous_value=prev_d,
                change_absolute=change_abs,
                change_percentage=change_pct,
            )
        )

    movers.sort(key=lambda m: abs(m.change_percentage), reverse=True)
    return movers
