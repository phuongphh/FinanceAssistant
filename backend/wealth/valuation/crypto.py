"""Crypto holding valuation using real market prices with safe fallback."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable

from backend.market_data.client import get_crypto_quote, get_fast_crypto_quotes
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


def _crypto_symbol(asset: Asset) -> str:
    extra = getattr(asset, "extra", None) or {}
    return str(extra.get("symbol") or extra.get("ticker") or asset.name).upper().strip()


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


async def value_crypto_holding(asset: Asset) -> HoldingValuation:
    """Value one crypto asset from market data; fallback keeps old user-entered price."""
    symbol = _crypto_symbol(asset)
    try:
        quote = await get_crypto_quote(symbol)
    except Exception as exc:
        logger.warning(
            "Crypto market data unavailable for %s; using user input price: %s",
            symbol,
            exc,
        )
        quote = None
    return _valuation_from_quote(asset, quote)


async def value_crypto_holdings(
    assets: Iterable[Asset],
) -> dict[Asset, HoldingValuation]:
    """Batch-value crypto holdings in a single provider call.

    User-facing handlers (``query_assets``, briefings) hit this path on
    every reply, so a portfolio with N coins shouldn't fan out into N
    sequential HTTP requests — that's the 10s+ tail we used to see for
    the asset-list reply. ``get_fast_crypto_quotes`` does one CoinGecko
    ``/simple/price?ids=...`` call with a 1.2s fail-fast timeout and
    transparent last-known fallback, which is what we want for an
    interactive reply.

    Non-crypto assets in ``assets`` are ignored. Crypto assets whose
    symbol the batch couldn't resolve fall back to the asset's stored
    ``avg_price`` / ``current_value`` and are flagged stale, matching
    the single-asset path.
    """
    crypto_assets = [
        a for a in assets if getattr(a, "asset_type", None) == "crypto"
    ]
    if not crypto_assets:
        return {}

    symbols = list({_crypto_symbol(a) for a in crypto_assets})
    quotes: dict[str, PriceQuote] = {}
    try:
        quotes = await get_fast_crypto_quotes(symbols)
    except Exception as exc:
        logger.warning(
            "Batch crypto quote fetch failed for %d symbols; using fallback prices: %s",
            len(symbols),
            exc,
        )

    return {
        asset: _valuation_from_quote(asset, quotes.get(_crypto_symbol(asset)))
        for asset in crypto_assets
    }
