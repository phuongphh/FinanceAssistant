"""Cache-first quote accessors used by jobs and wealth valuation."""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any, Protocol

from backend.config import get_settings
from backend.market_data.cache.cache_keys import quote_key
from backend.market_data.cache.price_cache import PriceCache
from backend.market_data.exceptions import ProviderUnavailable
from backend.market_data.normalizer import PriceQuote
from backend.market_data.providers.base_dispatcher import Dispatcher
from backend.market_data.providers.crypto_coingecko import CoinGeckoCryptoProvider
from backend.market_data.providers.stock_dispatcher import build_stock_dispatcher

logger = logging.getLogger(__name__)


class QuoteProvider(Protocol):
    async def fetch_quote(self, symbol: str) -> PriceQuote: ...
    async def fetch_batch(self, symbols: list[str]) -> list[PriceQuote]: ...


@lru_cache
def get_redis_client() -> Any:
    from redis.asyncio import Redis

    settings = get_settings()
    return Redis.from_url(settings.redis_url, decode_responses=True)


def get_price_cache() -> PriceCache:
    return PriceCache(get_redis_client())


def get_stock_provider() -> Dispatcher:
    return build_stock_dispatcher(get_redis_client(), timeout=get_settings().market_data_timeout_seconds)


def get_crypto_provider() -> CoinGeckoCryptoProvider:
    return CoinGeckoCryptoProvider(timeout=get_settings().market_data_timeout_seconds)


async def get_quote(asset_type: str, symbol: str, provider: QuoteProvider) -> PriceQuote:
    """Return cached quote first; otherwise fetch, cache, and fallback to last-known."""
    cache = get_price_cache()
    try:
        cached = await cache.get(quote_key(asset_type, symbol))
        if cached is not None:
            return cached
        quote = await provider.fetch_quote(symbol)
        await cache.set(quote)
        await cache.set_last_known(quote)
        return quote
    except Exception as exc:
        try:
            last_known = await cache.get_last_known(symbol, asset_type)
        except Exception:
            last_known = None
        if last_known is not None:
            logger.warning("Using stale %s quote for %s after provider error: %s", asset_type, symbol, exc)
            return last_known
        if isinstance(exc, ProviderUnavailable):
            raise
        raise ProviderUnavailable(f"Unable to fetch {asset_type} quote for {symbol}: {exc}") from exc


async def get_stock_quote(symbol: str) -> PriceQuote:
    return await get_quote("stock", symbol, get_stock_provider())


async def get_crypto_quote(symbol: str) -> PriceQuote:
    return await get_quote("crypto", symbol, get_crypto_provider())
