"""Stock holding valuation using real market prices with safe fallback."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable

from backend.market_data.client import get_stock_quote, get_stock_quotes
from backend.market_data.normalizer import PriceQuote
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


def _stock_symbol(asset: Asset) -> str:
    extra = getattr(asset, "extra", None) or {}
    return str(
        extra.get("ticker") or extra.get("symbol") or asset.name
    ).upper().strip()


def _valuation_from_quote(
    asset: Asset, quote: PriceQuote | None
) -> HoldingValuation:
    extra = getattr(asset, "extra", None) or {}
    quantity = _decimal_extra(extra, "quantity", Decimal(1))
    cost_basis = _decimal_extra(extra, "avg_price", _fallback_price(asset))
    if quote is not None:
        current_price = quote.price
        is_stale = quote.is_stale
    else:
        current_price = _fallback_price(asset)
        is_stale = True
    current_value = current_price * quantity
    pnl_pct = (
        None
        if cost_basis == 0
        else (current_price - cost_basis) / cost_basis * Decimal(100)
    )
    return HoldingValuation(
        current_price, quantity, cost_basis, current_value, pnl_pct, is_stale
    )


async def value_stock_holding(asset: Asset) -> HoldingValuation:
    """Value one stock asset from market data; fallback keeps old user-entered price."""
    symbol = _stock_symbol(asset)
    try:
        quote = await get_stock_quote(symbol)
    except Exception as exc:
        logger.warning(
            "Stock market data unavailable for %s; using user input price: %s",
            symbol,
            exc,
        )
        quote = None
    return _valuation_from_quote(asset, quote)


async def value_stock_holdings(
    assets: Iterable[Asset],
) -> dict[Asset, HoldingValuation]:
    """Batch-value stock holdings in a single provider call.

    Mirrors ``value_crypto_holdings`` — net-worth and dashboard paths
    used to fan out N HTTP calls (one per stock) which dominated
    latency for stock-heavy portfolios. ``get_stock_quotes`` dedupes
    cached symbols and asks the stock dispatcher for the rest in a
    single batch, with the existing last-known fallback on errors.

    Non-stock assets are ignored. Holdings whose symbol the batch
    couldn't resolve fall back to the stored ``avg_price`` and are
    flagged stale, mirroring the single-asset path.
    """
    stock_assets = [
        a for a in assets if getattr(a, "asset_type", None) == "stock"
    ]
    if not stock_assets:
        return {}

    symbols = list({_stock_symbol(a) for a in stock_assets})
    quotes: dict[str, PriceQuote] = {}
    try:
        quotes = await get_stock_quotes(symbols)
    except Exception as exc:
        logger.warning(
            "Batch stock quote fetch failed for %d symbols; using fallback prices: %s",
            len(symbols),
            exc,
        )

    return {
        asset: _valuation_from_quote(asset, quotes.get(_stock_symbol(asset)))
        for asset in stock_assets
    }
