"""Gold holding valuation using real market prices with safe fallback."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from backend.market_data.client import get_gold_quote
from backend.wealth.models.asset import Asset

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HoldingValuation:
    current_price: Decimal
    quantity: Decimal
    cost_basis: Decimal
    current_value: Decimal
    pnl_pct: Decimal | None
    is_stale: bool


def _decimal_extra(extra: dict[str, Any], key: str, default: Decimal = Decimal(0)) -> Decimal:
    value = extra.get(key)
    if value is None or value == "":
        return default
    return Decimal(str(value))


def _symbol(asset: Asset) -> str:
    extra = getattr(asset, "extra", None) or {}
    gold_type = str(extra.get("type") or extra.get("symbol") or asset.subtype or "SJC").upper()
    return "RING_24K" if "RING" in gold_type or "NH" in gold_type or "24K" in gold_type else "SJC_GOLD"


def _quantity(asset: Asset) -> Decimal:
    extra = getattr(asset, "extra", None) or {}
    if extra.get("quantity") is not None:
        return _decimal_extra(extra, "quantity", Decimal(1))
    if extra.get("tael") is not None:
        return _decimal_extra(extra, "tael", Decimal(1))
    if extra.get("weight_gram") is not None:
        return _decimal_extra(extra, "weight_gram", Decimal(0)) / Decimal("37.5")
    return Decimal(1)


def _fallback_price(asset: Asset) -> Decimal:
    quantity = _quantity(asset)
    extra = getattr(asset, "extra", None) or {}
    for key in ("avg_price", "user_input_price", "purchase_price"):
        if extra.get(key) is not None:
            return Decimal(str(extra[key]))
    if quantity > 0:
        return Decimal(asset.current_value or asset.initial_value or 0) / quantity
    return Decimal(asset.current_value or asset.initial_value or 0)


async def value_gold_holding(asset: Asset) -> HoldingValuation:
    """Value one gold asset from market data; fallback keeps old user-entered price."""
    symbol = _symbol(asset)
    quantity = _quantity(asset)
    cost_basis = _fallback_price(asset)
    is_stale = False
    try:
        quote = await get_gold_quote(symbol)
        current_price = quote.price
        is_stale = quote.is_stale
    except Exception as exc:
        logger.warning("Gold market data unavailable for %s; using user input price: %s", symbol, exc)
        current_price = _fallback_price(asset)
        is_stale = True
    current_value = current_price * quantity
    pnl_pct = None if cost_basis == 0 else (current_price - cost_basis) / cost_basis * Decimal(100)
    return HoldingValuation(current_price, quantity, cost_basis, current_value, pnl_pct, is_stale)
