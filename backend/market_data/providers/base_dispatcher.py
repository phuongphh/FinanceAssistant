"""Provider dispatcher with primary/secondary fallback and Redis circuit breaker."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Protocol

from backend.market_data.base import BaseProvider
from backend.market_data.cache.cache_keys import (
    health_failures_key,
    health_open_until_key,
)
from backend.market_data.exceptions import (
    MarketDataError,
    ParserError,
    ProviderUnavailable,
    RateLimitError,
)
from backend.market_data.normalizer import PriceQuote


class RedisLike(Protocol):
    """Subset of redis.asyncio.Redis used by Dispatcher."""

    async def get(self, key: str) -> str | bytes | None: ...
    async def setex(self, key: str, time: int, value: str) -> Any: ...
    async def incr(self, key: str) -> int: ...
    async def expire(self, key: str, time: int) -> Any: ...
    async def delete(self, *keys: str) -> int: ...


logger = logging.getLogger(__name__)

_FAILURE_THRESHOLD = 5
_FAILURE_WINDOW_SECONDS = 60
_OPEN_SECONDS = 300

_RETRYABLE_ERRORS = (
    asyncio.TimeoutError,
    TimeoutError,
    ProviderUnavailable,
    RateLimitError,
    ParserError,
)


class Dispatcher:
    """Fetch through primary provider first, falling back to secondary provider."""

    def __init__(
        self,
        primary: BaseProvider,
        secondary: BaseProvider,
        redis_client: RedisLike,
        timeout: float = 3.0,
    ) -> None:
        self.primary = primary
        self.secondary = secondary
        self.redis = redis_client
        self.timeout = timeout

    @property
    def asset_type(self) -> str:
        return self.primary.asset_type

    async def fetch_quote(self, symbol: str) -> PriceQuote:
        """Fetch one quote, using circuit state to decide provider order."""
        if not await self._is_circuit_open(self.primary):
            try:
                return await self._call_provider(self.primary, symbol)
            except _RETRYABLE_ERRORS as exc:
                await self._record_failure(self.primary)
                logger.warning(
                    "Primary provider failed for %s, falling back to secondary: %s",
                    symbol,
                    exc,
                )
        else:
            logger.info(
                "Circuit OPEN for %s; skipping primary for %s",
                self._provider_name(self.primary),
                symbol,
            )

        return await self._call_secondary(symbol)

    async def fetch_batch(self, symbols: list[str]) -> list[PriceQuote]:
        """Fetch many symbols with one provider request when circuits allow it.

        Jobs and backfills can ask for tens of symbols at once. Calling
        ``fetch_quote`` sequentially would multiply provider latency and keep
        hitting an already-open backup circuit. Use provider-native batch calls
        instead and apply the same circuit checks as single-quote fetches.

        Unlike single-quote fetches, a provider batch can *succeed* (no
        exception) yet return fewer symbols than requested — e.g. a 200 OK with
        an empty or shape-drifted body. Treat any symbol the primary did not
        return as missing and ask the secondary provider for it, so a healthy
        backup (SSI) still serves quotes when the primary (VNDIRECT) answers
        emptily. Without this guard the empty primary result would be returned
        as-is and the secondary would never be consulted.
        """
        clean_symbols = [symbol for symbol in symbols if symbol.strip()]
        if not clean_symbols:
            return []

        quotes: list[PriceQuote] = []
        if not await self._is_circuit_open(self.primary):
            try:
                quotes = await self._call_provider_batch(self.primary, clean_symbols)
            except _RETRYABLE_ERRORS as exc:
                await self._record_failure(self.primary)
                logger.warning(
                    "Primary provider failed for batch of %d symbols, falling back to secondary: %s",
                    len(clean_symbols),
                    exc,
                )
        else:
            logger.info(
                "Circuit OPEN for %s; skipping primary batch of %d symbols",
                self._provider_name(self.primary),
                len(clean_symbols),
            )

        missing = self._missing_symbols(clean_symbols, quotes)
        if not missing:
            return quotes

        if quotes:
            logger.info(
                "Primary %s returned %d/%d symbols; asking secondary for the remaining %d",
                self._provider_name(self.primary),
                len(quotes),
                len(clean_symbols),
                len(missing),
            )
        try:
            secondary_quotes = await self._call_secondary_batch(missing)
        except MarketDataError:
            # Keep whatever the primary already gave us; only surface the error
            # when we have nothing at all (preserves the single-quote raise
            # contract). This also covers non-retryable errors such as
            # SymbolNotFound for one missing ticker, which must not discard the
            # valid quotes the primary returned for the rest of the batch.
            if quotes:
                return quotes
            raise
        return quotes + secondary_quotes

    @staticmethod
    def _missing_symbols(requested: list[str], quotes: list[PriceQuote]) -> list[str]:
        """Return requested symbols not present in ``quotes`` (case-insensitive)."""
        have = {quote.symbol.upper() for quote in quotes}
        return [symbol for symbol in requested if symbol.upper().strip() not in have]

    async def _call_secondary(self, symbol: str) -> PriceQuote:
        if await self._is_circuit_open(self.secondary):
            name = self._provider_name(self.secondary)
            logger.info("Circuit OPEN for %s; skipping secondary for %s", name, symbol)
            raise ProviderUnavailable(f"Circuit open for {name}")
        try:
            return await self._call_provider(self.secondary, symbol)
        except _RETRYABLE_ERRORS:
            await self._record_failure(self.secondary)
            raise

    async def _call_secondary_batch(self, symbols: list[str]) -> list[PriceQuote]:
        if await self._is_circuit_open(self.secondary):
            name = self._provider_name(self.secondary)
            logger.info(
                "Circuit OPEN for %s; skipping secondary batch of %d symbols",
                name,
                len(symbols),
            )
            raise ProviderUnavailable(f"Circuit open for {name}")
        try:
            return await self._call_provider_batch(self.secondary, symbols)
        except _RETRYABLE_ERRORS:
            await self._record_failure(self.secondary)
            raise

    async def _call_provider(self, provider: BaseProvider, symbol: str) -> PriceQuote:
        quote = await asyncio.wait_for(
            provider.fetch_quote(symbol), timeout=self.timeout
        )
        await self._record_success(provider)
        return quote

    async def _call_provider_batch(
        self, provider: BaseProvider, symbols: list[str]
    ) -> list[PriceQuote]:
        quotes = await asyncio.wait_for(
            provider.fetch_batch(symbols), timeout=self.timeout
        )
        if quotes:
            await self._record_success(provider)
        elif symbols:
            # 200-but-empty for a non-empty request mirrors the single-quote
            # ParserError-on-empty path: count it as a failure so the circuit
            # can open instead of silently resetting on a dead-but-OK provider.
            await self._record_failure(provider)
        return quotes

    async def _is_circuit_open(self, provider: BaseProvider) -> bool:
        name = self._provider_name(provider)
        raw = await self.redis.get(health_open_until_key(name))
        if raw is None:
            return False
        open_until = float(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
        if open_until > time.time():
            return True
        logger.info("Circuit HALF-OPEN for %s, testing", name)
        return False

    async def _record_failure(self, provider: BaseProvider) -> None:
        name = self._provider_name(provider)
        failures_key = health_failures_key(name)
        failures = int(await self.redis.incr(failures_key))
        if failures == 1:
            await self.redis.expire(failures_key, _FAILURE_WINDOW_SECONDS)
        if failures >= _FAILURE_THRESHOLD:
            await self._open_circuit(name)

    async def _record_success(self, provider: BaseProvider) -> None:
        name = self._provider_name(provider)
        deleted = await self.redis.delete(
            health_failures_key(name), health_open_until_key(name)
        )
        if deleted:
            logger.info("Circuit CLOSED for %s", name)

    async def _open_circuit(self, provider_name: str) -> None:
        open_until = time.time() + _OPEN_SECONDS
        await self.redis.setex(
            health_open_until_key(provider_name), _OPEN_SECONDS, str(open_until)
        )
        logger.warning("Circuit OPEN for %s", provider_name)

    @staticmethod
    def _provider_name(provider: BaseProvider) -> str:
        return str(getattr(provider, "name", provider.__class__.__name__)).lower()
