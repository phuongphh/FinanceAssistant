"""Gold holding valuation using real market prices with safe fallback."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable

from backend.market_data.client import get_gold_quote, get_gold_quotes
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


def _valuation_from_quote(
    asset: Asset, quote: PriceQuote | None
) -> HoldingValuation:
    quantity = _quantity(asset)
    cost_basis = _fallback_price(asset)
    if quote is not None:
        current_price = quote.price
        is_stale = quote.is_stale
    else:
        current_price = _fallback_price(asset)
        is_stale = True
    current_value = current_price * quantity
    pnl_pct = None if cost_basis == 0 else (current_price - cost_basis) / cost_basis * Decimal(100)
    return HoldingValuation(current_price, quantity, cost_basis, current_value, pnl_pct, is_stale)


async def value_gold_holding(asset: Asset) -> HoldingValuation:
    """Value one gold asset from market data; fallback keeps old user-entered price."""
    symbol = _symbol(asset)
    try:
        quote = await get_gold_quote(symbol)
    except Exception as exc:
        logger.warning("Gold market data unavailable for %s; using user input price: %s", symbol, exc)
        quote = None
    return _valuation_from_quote(asset, quote)


async def value_gold_holdings(
    assets: Iterable[Asset],
) -> dict[Asset, HoldingValuation]:
    """Batch-value gold holdings in a single provider call.

    Mirrors ``value_stock_holdings`` / ``value_crypto_holdings`` so the
    interactive net-worth and asset-list paths can live-quote gold without
    fanning out one HTTP call per bar. Gold resolves to just a couple of
    symbols (``SJC_GOLD`` / ``RING_24K``) so the batch is tiny, but it keeps
    the valuation basis identical across asset classes.

    Non-gold assets are ignored. Holdings whose symbol the batch couldn't
    resolve fall back to the stored price and are flagged stale, mirroring
    the single-asset path.
    """
    gold_assets = [
        a for a in assets if getattr(a, "asset_type", None) == "gold"
    ]
    if not gold_assets:
        return {}

    symbols = list({_symbol(a) for a in gold_assets})
    quotes: dict[str, PriceQuote] = {}
    try:
        quotes = await get_gold_quotes(symbols)
    except Exception as exc:
        logger.warning(
            "Batch gold quote fetch failed for %d symbols; using fallback prices: %s",
            len(symbols),
            exc,
        )

    return {
        asset: _valuation_from_quote(asset, quotes.get(_symbol(asset)))
        for asset in gold_assets
    }
