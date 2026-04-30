"""Aggregation helpers for the Mini App wealth dashboard.

Composes ``net_worth_calculator`` + ``asset_service`` + ``ladder`` into the
single response payload that ``/miniapp/api/wealth/overview`` returns.

Layer contract: this is a service — it takes a session, flushes nothing,
and returns plain dicts ready to JSON-serialize. No commits, no transport
calls. Heavy reads (trend, breakdown) are factored out so the route can
also serve them à la carte via ``/miniapp/api/wealth/trend``.

Performance: the ``trend`` query uses ``DISTINCT ON (asset_id)`` per day,
which is the same shape as ``calculate_historical`` but batched across the
window. For a user with ~10 assets and 365 days this is one round-trip,
~1ms in Postgres.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.wealth.asset_types import get_asset_config, get_subtype_label
from backend.wealth.ladder import WealthLevel, detect_level, next_milestone
from backend.wealth.services import asset_service, net_worth_calculator

# Trend window options the Mini App exposes in its period selector.
TREND_DAYS_ALLOWED = (30, 90, 365)


_LEVEL_LABELS_VI = {
    WealthLevel.STARTER: "Khởi đầu",
    WealthLevel.YOUNG_PROFESSIONAL: "Young Professional",
    WealthLevel.MASS_AFFLUENT: "Mass Affluent",
    WealthLevel.HIGH_NET_WORTH: "High Net Worth",
}


def _group_key(asset) -> tuple[str, str, str]:
    """Identity for asset aggregation on the dashboard.

    Same name (case + whitespace insensitive) + same subtype + same
    asset_type → merged into one card. Different subtypes stay separate
    even if the name matches: a Techcombank checking and a Techcombank
    savings are functionally different products and the user benefits
    from seeing them apart.
    """
    name = (asset.name or "").strip().casefold()
    return (asset.asset_type, asset.subtype or "", name)


def _serialize_group(members: list) -> dict:
    """Aggregate a list of assets sharing the same identity into one card.

    Members must already be pre-grouped by ``_group_key``. Values are
    summed, ``acquired_at`` is the earliest of any member, and the
    ``count`` / ``member_ids`` fields let the frontend annotate rows
    that bundle multiple raw entries (e.g. ``×2`` badge).
    """
    first = members[0]
    asset_type = first.asset_type
    subtype = first.subtype
    config = get_asset_config(asset_type)

    initial = sum((Decimal(m.initial_value or 0) for m in members), Decimal(0))
    current = sum((Decimal(m.current_value or 0) for m in members), Decimal(0))
    change = current - initial
    change_pct = float(change / initial * 100) if initial > 0 else 0.0

    acquired_dates = [m.acquired_at for m in members if m.acquired_at]
    earliest = min(acquired_dates) if acquired_dates else None

    return {
        "id": str(first.id),
        "name": first.name,
        "asset_type": asset_type,
        "subtype": subtype,
        "subtype_label": get_subtype_label(subtype),
        "icon": config.get("icon", "📌"),
        "type_label": config.get("label_vi", asset_type),
        "current_value": float(current),
        "initial_value": float(initial),
        "change": float(change),
        "change_pct": round(change_pct, 2),
        "acquired_at": earliest.isoformat() if earliest else None,
        "count": len(members),
        "member_ids": [str(m.id) for m in members],
    }


def _group_assets(assets: list) -> list[dict]:
    """Group raw asset rows into dashboard cards, sorted largest-first.

    Two rows with the same name + subtype merge into one card with
    summed values. Different subtypes stay separate. Sorting by current
    value puts the user's biggest holdings on top — what they care
    about glancing at first.
    """
    groups: dict[tuple[str, str, str], list] = defaultdict(list)
    for a in assets:
        groups[_group_key(a)].append(a)

    serialized = [_serialize_group(members) for members in groups.values()]
    serialized.sort(key=lambda g: g["current_value"], reverse=True)
    return serialized


def _build_breakdown(
    by_type: dict[str, Decimal], total: Decimal
) -> list[dict]:
    """Sort by value desc, attach icon/label/color/pct from YAML config."""
    breakdown: list[dict] = []
    total_f = float(total) if total else 0.0
    for asset_type, value in by_type.items():
        cfg = get_asset_config(asset_type)
        v = float(value)
        pct = (v / total_f * 100) if total_f > 0 else 0.0
        breakdown.append(
            {
                "asset_type": asset_type,
                "label": cfg.get("label_vi", asset_type),
                "icon": cfg.get("icon", "📌"),
                "color": cfg.get("color", "#9CA3AF"),
                "value": v,
                "pct": round(pct, 2),
            }
        )
    breakdown.sort(key=lambda x: x["value"], reverse=True)
    return breakdown


async def get_trend(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    days: int = 90,
    end: date | None = None,
) -> list[dict]:
    """Daily net worth series over ``days`` ending on ``end`` (default today).

    For each day we sum the latest snapshot per asset on/before that day.
    Days with no historical data return 0 — frontend can render empty state.
    """
    if days not in TREND_DAYS_ALLOWED:
        # Defensive — route already validates, but make the service robust
        # to direct callers (tests, admin scripts).
        raise ValueError(f"days must be one of {TREND_DAYS_ALLOWED}")

    end_date = end or date.today()
    start_date = end_date - timedelta(days=days - 1)

    # One query per day would be N round-trips. Instead, produce a
    # generated date series in SQL, LATERAL-join the latest snapshot per
    # asset on/before that day, sum across assets. Cheap on Postgres.
    # Postgres ``::`` cast confuses SQLAlchemy's bindparam regex, so we use
    # ``CAST(... AS date)`` instead. Auto-detect of bind keys from ``:name``
    # keeps this readable without an explicit ``bindparams()`` declaration.
    stmt = text(
        """
        WITH days AS (
            SELECT generate_series(
                CAST(:start_date AS date),
                CAST(:end_date AS date),
                INTERVAL '1 day'
            )::date AS day
        )
        SELECT
            d.day AS day,
            COALESCE(SUM(latest.value), 0) AS total
        FROM days d
        LEFT JOIN LATERAL (
            SELECT DISTINCT ON (s.asset_id) s.value
            FROM asset_snapshots s
            WHERE s.user_id = :user_id
              AND s.snapshot_date <= d.day
            ORDER BY s.asset_id, s.snapshot_date DESC
        ) latest ON TRUE
        GROUP BY d.day
        ORDER BY d.day
        """
    )
    rows = (
        await db.execute(
            stmt,
            {
                "start_date": start_date,
                "end_date": end_date,
                "user_id": user_id,
            },
        )
    ).all()

    return [
        {"date": row.day.isoformat(), "value": float(row.total or 0)}
        for row in rows
    ]


async def build_overview(
    db: AsyncSession, user_id: uuid.UUID, *, trend_days: int = 90
) -> dict:
    """One-shot dashboard payload — net worth + change + breakdown + trend + assets."""
    breakdown_now = await net_worth_calculator.calculate(db, user_id)
    change_day = await net_worth_calculator.calculate_change(
        db, user_id, net_worth_calculator.PERIOD_DAY
    )
    change_month = await net_worth_calculator.calculate_change(
        db, user_id, net_worth_calculator.PERIOD_MONTH
    )

    level = detect_level(breakdown_now.total)
    target_amount, target_level = next_milestone(breakdown_now.total)

    trend = await get_trend(db, user_id, days=trend_days)
    assets = await asset_service.get_user_assets(db, user_id)
    grouped_assets = _group_assets(assets)

    breakdown = _build_breakdown(breakdown_now.by_type, breakdown_now.total)

    target_pct = 0.0
    if target_amount > 0:
        target_pct = round(
            min(100.0, float(breakdown_now.total / target_amount * 100)), 2
        )

    payload = {
        "net_worth": float(breakdown_now.total),
        # Logical card count, not raw row count: the user thinks of
        # two ``Tiền mặt`` entries as one bucket, so the hero pill
        # should match what they see in the asset list below.
        "asset_count": len(grouped_assets),
        "currency": breakdown_now.currency,
        "level": level.value,
        "level_label": _LEVEL_LABELS_VI.get(level, level.value),
        "change_day": {
            "amount": float(change_day.change_absolute),
            "pct": round(change_day.change_percentage, 2),
        },
        "change_month": {
            "amount": float(change_month.change_absolute),
            "pct": round(change_month.change_percentage, 2),
        },
        "breakdown": breakdown,
        "trend": trend,
        "trend_days": trend_days,
        "assets": grouped_assets,
        "next_milestone": {
            "target": float(target_amount),
            "target_level": target_level.value,
            "target_label": _LEVEL_LABELS_VI.get(target_level, target_level.value),
            "pct_progress": target_pct,
            "remaining": float(max(Decimal(0), target_amount - breakdown_now.total)),
        },
    }
    return payload
