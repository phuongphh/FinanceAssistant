"""CoinGecko free-tier crypto price provider."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Awaitable, Callable

import httpx

from backend.market_data.base import BaseProvider
from backend.market_data.exceptions import ParserError, ProviderUnavailable, RateLimitError, SymbolNotFound
from backend.market_data.normalizer import PriceQuote
from backend.market_data.providers.coingecko_symbols import COINGECKO_SYMBOLS
from backend.market_data.providers.http_utils import require_decimal

SleepFunc = Callable[[float], Awaitable[None]]


class CoinGeckoCryptoProvider(BaseProvider):
    """Fetch crypto prices from CoinGecko simple price API."""

    name = "coingecko"

    def __init__(
        self,
        *,
        base_url: str = "https://api.coingecko.com/api/v3",
        timeout: float = 3.0,
        client: httpx.AsyncClient | None = None,
        sleep: SleepFunc = asyncio.sleep,
        rate_limit_retry_delays: tuple[float, ...] = (1, 2, 4),
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = client
        self._sleep = sleep
        self._rate_limit_retry_delays = rate_limit_retry_delays

    @property
    def asset_type(self) -> str:
        return "crypto"

    async def fetch_quote(self, symbol: str) -> PriceQuote:
        quotes = await self.fetch_batch([symbol])
        if not quotes:
            raise SymbolNotFound(symbol)
        return quotes[0]

    async def fetch_batch(self, symbols: list[str]) -> list[PriceQuote]:
        clean_symbols = [symbol.upper().strip() for symbol in symbols if symbol.strip()]
        if not clean_symbols:
            return []
        unknown = [symbol for symbol in clean_symbols if symbol not in COINGECKO_SYMBOLS]
        if unknown:
            raise SymbolNotFound(f"Unsupported crypto symbol(s): {', '.join(unknown)}")
        ids_by_symbol = {symbol: COINGECKO_SYMBOLS[symbol] for symbol in clean_symbols}
        payload = await self._get_json(
            "/simple/price",
            params={
                "ids": ",".join(ids_by_symbol.values()),
                "vs_currencies": "usd,vnd",
                "include_24hr_change": "true",
                "include_24hr_vol": "true",
            },
        )
        fetched_at = datetime.now(timezone.utc)
        quotes: list[PriceQuote] = []
        for symbol, coin_id in ids_by_symbol.items():
            data = payload.get(coin_id) if isinstance(payload, dict) else None
            if not isinstance(data, dict):
                raise SymbolNotFound(f"CoinGecko missing data for {symbol}")
            price = require_decimal(data.get("vnd"), "vnd")
            quotes.append(
                PriceQuote(
                    symbol=symbol,
                    price=price,
                    currency="VND",
                    asset_type="crypto",
                    fetched_at=fetched_at,
                    source="coingecko",
                    metadata={
                        "coin_id": coin_id,
                        "usd": require_decimal(data.get("usd"), "usd") if data.get("usd") is not None else None,
                        "change_pct_24h": require_decimal(data.get("vnd_24h_change"), "vnd_24h_change") if data.get("vnd_24h_change") is not None else None,
                        "volume_24h": require_decimal(data.get("vnd_24h_vol"), "vnd_24h_vol") if data.get("vnd_24h_vol") is not None else None,
                    },
                )
            )
        return quotes

    async def _get_json(self, path: str, *, params: dict[str, str]) -> Any:
        delays = self._rate_limit_retry_delays
        last_rate_limit: RateLimitError | None = None
        for attempt in range(len(delays) + 1):
            response = await self._request(path, params=params)
            if response.status_code != 429:
                self._raise_for_status(response)
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ParserError("CoinGecko returned unsupported payload")
                return payload
            last_rate_limit = RateLimitError("CoinGecko rate limit reached")
            if attempt < len(delays):
                await self._sleep(delays[attempt])
        raise last_rate_limit or RateLimitError("CoinGecko rate limit reached")

    async def _request(self, path: str, *, params: dict[str, str]) -> httpx.Response:
        if self._client is not None:
            return await self._client.get(path, params=params)
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            return await client.get(path, params=params)

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code == 404:
            raise SymbolNotFound("CoinGecko symbol not found")
        if 400 <= response.status_code < 500:
            raise ProviderUnavailable(f"CoinGecko client error {response.status_code}")
        if response.status_code >= 500:
            raise ProviderUnavailable(f"CoinGecko server error {response.status_code}")
