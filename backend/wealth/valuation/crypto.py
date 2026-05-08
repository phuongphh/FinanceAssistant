"""Crypto holding valuation using real market prices with safe fallback."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from backend.market_data.client import get_crypto_quote
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


def _fallback_price(asset: Asset) -> Decimal:
    extra = getattr(asset, "extra", None) or {}
    quantity = _decimal_extra(extra, "quantity", Decimal(0))
    if extra.get("avg_price") is not None:
        return Decimal(str(extra["avg_price"]))
    if quantity > 0:
        return Decimal(asset.current_value or asset.initial_value or 0) / quantity
    return Decimal(asset.current_value or asset.initial_value or 0)


async def value_crypto_holding(asset: Asset) -> HoldingValuation:
    """Value one crypto asset from market data; fallback keeps old user-entered price."""
    extra = getattr(asset, "extra", None) or {}
    symbol = str(extra.get("symbol") or extra.get("ticker") or asset.name).upper().strip()
    quantity = _decimal_extra(extra, "quantity", Decimal(1))
    cost_basis = _decimal_extra(extra, "avg_price", _fallback_price(asset))
    is_stale = False
    try:
        quote = await get_crypto_quote(symbol)
        current_price = quote.price
        is_stale = quote.is_stale
    except Exception as exc:
        logger.warning("Crypto market data unavailable for %s; using user input price: %s", symbol, exc)
        current_price = _fallback_price(asset)
        is_stale = True
    current_value = current_price * quantity
    pnl_pct = None if cost_basis == 0 else (current_price - cost_basis) / cost_basis * Decimal(100)
    return HoldingValuation(current_price, quantity, cost_basis, current_value, pnl_pct, is_stale)
