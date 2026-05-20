"""Portfolio analytics for Phase 3.9 briefings."""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, select

from backend.database import get_session_factory
from backend.models.stock_historical_price import StockHistoricalPrice
from backend.wealth.models.asset import Asset
from backend.wealth.valuation.crypto import value_crypto_holding
from backend.wealth.valuation.gold import value_gold_holding
from backend.wealth.valuation.stock import value_stock_holding

logger = logging.getLogger(__name__)

# Asset types eligible for "best/worst performer" ranking. Cash, real_estate,
# and other are intentionally excluded:
#   - cash: initial_value is the onboarding snapshot, not a cost basis. As the
#     user's balance changes, (current - initial)/initial yields a meaningless
#     "return %" that confuses users and can grow unbounded.
#   - real_estate: no daily price feed; using stale cost basis is misleading.
#   - other: unstructured asset class; can't trust the percentage.
_PERFORMANCE_ELIGIBLE_TYPES: frozenset[str] = frozenset({"stock", "crypto", "gold"})

# Sanity bounds on return percentages displayed to users. Anything outside this
# band is almost always a data-quality bug (typo in avg_price, wrong unit,
# placeholder cost basis). We exclude such holdings from rankings and log a
# warning for ops investigation instead of rendering absurd numbers like
# "+29099900%" or "-4569%" that destroy user trust.
_MIN_REASONABLE_RETURN_PCT: Decimal = Decimal("-100")  # long position floor
_MAX_REASONABLE_RETURN_PCT: Decimal = Decimal("1000")  # 10x in any briefing window = data error


@dataclass(frozen=True)
class HoldingPerformance:
    asset_id: Any
    symbol: str
    asset_type: str
    current_value: Decimal
    cost_basis_value: Decimal
    return_pct: Decimal | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "symbol": self.symbol,
            "asset_type": self.asset_type,
            "current_value": self.current_value,
            "cost_basis_value": self.cost_basis_value,
            "return_pct": self.return_pct,
        }


def _symbol(asset: Asset) -> str:
    extra = asset.extra or {}
    return str(extra.get("ticker") or extra.get("symbol") or asset.name or asset.id).upper()


async def _value_asset(asset: Asset) -> tuple[Decimal, Decimal, Decimal | None]:
    if asset.asset_type == "stock":
        valuation = await value_stock_holding(asset)
        return valuation.current_value, valuation.cost_basis * valuation.quantity, valuation.pnl_pct
    if asset.asset_type == "crypto":
        valuation = await value_crypto_holding(asset)
        return valuation.current_value, valuation.cost_basis * valuation.quantity, valuation.pnl_pct
    if asset.asset_type == "gold":
        valuation = await value_gold_holding(asset)
        return valuation.current_value, valuation.cost_basis * valuation.quantity, valuation.pnl_pct
    current = Decimal(asset.current_value or 0)
    cost = Decimal(asset.initial_value or 0)
    pct = None if cost == 0 else (current - cost) / cost * Decimal(100)
    return current, cost, pct


async def _active_assets(db, user_id) -> list[Asset]:
    result = await db.execute(select(Asset).where(Asset.user_id == user_id, Asset.is_active.is_(True)))
    return list(result.scalars().all())


async def _latest_ytd_price(db, symbol: str, year_start: date) -> Decimal | None:
    result = await db.execute(
        select(StockHistoricalPrice.close_price)
        .where(StockHistoricalPrice.symbol == symbol, StockHistoricalPrice.price_date <= year_start)
        .order_by(desc(StockHistoricalPrice.price_date))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def compute_ytd_return(user_id) -> dict[str, Any]:
    """Return YTD performance from seeded Jan-1 prices where available."""
    year_start = date(date.today().year, 1, 1)
    async with get_session_factory()() as db:
        assets = await _active_assets(db, user_id)
        rows: list[dict[str, Any]] = []
        total_current = Decimal(0)
        total_start = Decimal(0)
        for asset in assets:
            current, cost, pct = await _value_asset(asset)
            start_value = cost
            if asset.asset_type == "stock":
                extra = asset.extra or {}
                qty = Decimal(str(extra.get("quantity") or 1))
                seeded = await _latest_ytd_price(db, _symbol(asset), year_start)
                if seeded is not None:
                    start_value = Decimal(seeded) * qty
            absolute = current - start_value
            row_pct = None if start_value == 0 else absolute / start_value * Decimal(100)
            rows.append({
                "asset_id": asset.id,
                "symbol": _symbol(asset),
                "asset_type": asset.asset_type,
                "current_value": current,
                "start_value": start_value,
                "absolute": absolute,
                "return_pct": row_pct if row_pct is not None else pct,
            })
            total_current += current
            total_start += start_value
    absolute = total_current - total_start
    return {
        "available": bool(rows) and total_start > 0,
        "return_pct": None if total_start == 0 else absolute / total_start * Decimal(100),
        "absolute": absolute,
        "by_holding": rows,
    }


async def get_best_worst_from_assets(assets: list[Asset]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Return (best, worst) holding by return % among investment positions.

    Cash, real_estate, and other assets are excluded — they have no meaningful
    investment return. Holdings whose computed return % falls outside
    ``[_MIN_REASONABLE_RETURN_PCT, _MAX_REASONABLE_RETURN_PCT]`` are also
    excluded (with a warning log) because such values indicate corrupted
    cost-basis data rather than real performance.
    """
    performances: list[HoldingPerformance] = []
    for asset in assets:
        if asset.asset_type not in _PERFORMANCE_ELIGIBLE_TYPES:
            continue
        current, cost, pct = await _value_asset(asset)
        if pct is None:
            continue
        if pct < _MIN_REASONABLE_RETURN_PCT or pct > _MAX_REASONABLE_RETURN_PCT:
            logger.warning(
                "Holding %s (asset_id=%s) excluded from best/worst: "
                "return_pct=%s out of range [%s, %s]; cost_basis_value=%s, current_value=%s",
                _symbol(asset), asset.id, pct,
                _MIN_REASONABLE_RETURN_PCT, _MAX_REASONABLE_RETURN_PCT,
                cost, current,
            )
            continue
        performances.append(HoldingPerformance(asset.id, _symbol(asset), asset.asset_type, current, cost, pct))
    if not performances:
        return None, None
    sorted_rows = sorted(performances, key=lambda row: row.return_pct or Decimal(0), reverse=True)
    return sorted_rows[0].to_dict(), sorted_rows[-1].to_dict()


async def get_best_worst_performer(user_id) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Return top and bottom active holding by P/L percentage."""
    async with get_session_factory()() as db:
        assets = await _active_assets(db, user_id)
    return await get_best_worst_from_assets(assets)


def compute_diversification_score(portfolio: list[Any]) -> dict[str, Any]:
    """Score 0-100 from number of asset classes and concentration risk."""
    by_type: dict[str, Decimal] = defaultdict(Decimal)
    for item in portfolio:
        if isinstance(item, dict):
            asset_type = str(item.get("asset_type") or "other")
            value = Decimal(str(item.get("value") or item.get("current_value") or 0))
        else:
            asset_type = str(getattr(item, "asset_type", "other") or "other")
            value = Decimal(getattr(item, "current_value", 0) or 0)
        if value > 0:
            by_type[asset_type] += value
    total = sum(by_type.values(), Decimal(0))
    if total <= 0:
        return {"score": 0, "label": "Yếu", "details": {}}
    type_score = min(len(by_type), 4) / Decimal(4) * Decimal(40)
    max_weight = max(by_type.values()) / total
    concentration_score = max(Decimal(0), Decimal(1) - max_weight) * Decimal(60)
    score = int((type_score + concentration_score).quantize(Decimal("1")))
    label = "Tốt" if score >= 70 else "Trung bình" if score >= 40 else "Yếu"
    return {
        "score": score,
        "label": label,
        "details": {asset_type: float(value / total) for asset_type, value in by_type.items()},
    }
