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
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.wealth.asset_types import get_asset_config
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


def _serialize_asset(asset) -> dict:
    """Trim asset ORM object → dashboard JSON shape."""
    config = get_asset_config(asset.asset_type)
    initial = Decimal(asset.initial_value or 0)
    current = Decimal(asset.current_value or 0)
    change = current - initial
    if initial > 0:
        change_pct = float(change / initial * 100)
    else:
        change_pct = 0.0

    return {
        "id": str(asset.id),
        "name": asset.name,
        "asset_type": asset.asset_type,
        "subtype": asset.subtype,
        "icon": config.get("icon", "📌"),
        "type_label": config.get("label_vi", asset.asset_type),
        "current_value": float(current),
        "initial_value": float(initial),
        "change": float(change),
        "change_pct": round(change_pct, 2),
        "acquired_at": asset.acquired_at.isoformat() if asset.acquired_at else None,
    }


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

    breakdown = _build_breakdown(breakdown_now.by_type, breakdown_now.total)

    target_pct = 0.0
    if target_amount > 0:
        target_pct = round(
            min(100.0, float(breakdown_now.total / target_amount * 100)), 2
        )

    payload = {
        "net_worth": float(breakdown_now.total),
        "asset_count": breakdown_now.asset_count,
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
        "assets": [_serialize_asset(a) for a in assets],
        "next_milestone": {
            "target": float(target_amount),
            "target_level": target_level.value,
            "target_label": _LEVEL_LABELS_VI.get(target_level, target_level.value),
            "pct_progress": target_pct,
            "remaining": float(max(Decimal(0), target_amount - breakdown_now.total)),
        },
    }
    return payload
