"""Redis-backed price cache with per-asset TTLs and last-known fallback."""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol

from backend.market_data.cache.cache_keys import asset_pattern, last_known_key, quote_key
from backend.market_data.normalizer import PriceQuote


class RedisLike(Protocol):
    """Subset of redis.asyncio.Redis used by PriceCache."""

    async def get(self, key: str) -> str | bytes | None: ...
    async def set(self, key: str, value: str) -> Any: ...
    async def setex(self, key: str, time: int, value: str) -> Any: ...
    async def delete(self, *keys: str) -> int: ...
    def scan_iter(self, match: str) -> Any: ...

TTL_SECONDS: dict[str, int] = {
    "stock": 300,
    "crypto": 120,
    "gold": 3600,
    "bank_rate": 604800,
    "news": 1800,
}


class PriceCache:
    """Small async wrapper around ``redis.asyncio.Redis`` for PriceQuote data."""

    def __init__(self, redis_client: RedisLike):
        self.redis = redis_client

    @staticmethod
    def key_for(asset_type: str, symbol: str) -> str:
        return quote_key(asset_type, symbol)

    @staticmethod
    def last_known_key_for(asset_type: str, symbol: str) -> str:
        return last_known_key(asset_type, symbol)

    async def get(self, key: str) -> PriceQuote | None:
        """Return a cached quote by exact key, or ``None`` on miss/expiry."""
        raw = await self.redis.get(key)
        if raw is None:
            return None
        return PriceQuote.from_json(raw)

    async def set(self, quote: PriceQuote) -> None:
        """Store quote under the standard key using the asset-type TTL."""
        ttl = TTL_SECONDS[quote.asset_type]
        await self.redis.setex(quote_key(quote.asset_type, quote.symbol), ttl, quote.to_json())

    async def set_last_known(self, quote: PriceQuote) -> None:
        """Store last-known quote without TTL; later writes win."""
        await self.redis.set(last_known_key(quote.asset_type, quote.symbol), quote.to_json())

    async def get_last_known(
        self,
        symbol: str,
        asset_type: str | None = None,
    ) -> PriceQuote | None:
        """Return last-known quote, optionally scoped to an asset type."""
        asset_types = [asset_type.lower()] if asset_type else list(TTL_SECONDS)
        for candidate_type in asset_types:
            raw = await self.redis.get(last_known_key(candidate_type, symbol))
            if raw is not None:
                return PriceQuote.from_json(raw).mark_stale()
        return None

    async def flush_asset_type(self, asset_type: str) -> int:
        """Delete all market-data keys for one asset type and return count."""
        keys: list[str] = []
        scanner = self.redis.scan_iter(match=asset_pattern(asset_type))
        if isinstance(scanner, AsyncIterator):
            async for key in scanner:
                keys.append(key.decode("utf-8") if isinstance(key, bytes) else key)
        else:
            for key in scanner:
                keys.append(key.decode("utf-8") if isinstance(key, bytes) else key)
        if not keys:
            return 0
        return int(await self.redis.delete(*keys))
