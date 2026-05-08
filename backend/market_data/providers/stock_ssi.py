"""SSI iBoard provider for Vietnamese stock quotes."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import httpx

from backend.market_data.base import BaseProvider
from backend.market_data.exceptions import ParserError, ProviderUnavailable, RateLimitError, SymbolNotFound
from backend.market_data.normalizer import PriceQuote
from backend.market_data.providers.http_utils import decimal_or_none, first_present, require_decimal, unwrap_first_record


class SSIStockProvider(BaseProvider):
    """Fetch and normalize SSI iBoard stock quotes."""

    name = "ssi"

    def __init__(
        self,
        *,
        base_url: str = "https://iboard.ssi.com.vn/dchart/api",
        timeout: float = 3.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = client

    @property
    def asset_type(self) -> str:
        return "stock"

    async def fetch_quote(self, symbol: str) -> PriceQuote:
        symbol = symbol.upper().strip()
        payload = await self._get_json("/1.1/defaultAllStocks", params={"symbol": symbol})
        record = self._find_symbol_record(payload, symbol)
        return self._parse_record(record, symbol)

    async def fetch_batch(self, symbols: list[str]) -> list[PriceQuote]:
        clean_symbols = [symbol.upper().strip() for symbol in symbols if symbol.strip()]
        if not clean_symbols:
            return []
        try:
            payload = await self._get_json(
                "/1.1/defaultAllStocks",
                params={"symbols": ",".join(clean_symbols)},
            )
            records = self._unwrap_records(payload)
            by_symbol = {
                str(first_present(record, ("symbol", "stockSymbol", "code", "ticker")) or "").upper(): record
                for record in records
            }
            if by_symbol:
                return [self._parse_record(by_symbol[symbol], symbol) for symbol in clean_symbols if symbol in by_symbol]
        except (ParserError, SymbolNotFound):
            pass
        return await asyncio.gather(*(self.fetch_quote(symbol) for symbol in clean_symbols))

    async def _get_json(self, path: str, *, params: dict[str, str]) -> Any:
        async def request(client: httpx.AsyncClient) -> httpx.Response:
            return await client.get(path, params=params)

        if self._client is not None:
            response = await request(self._client)
        else:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
                response = await request(client)
        self._raise_for_status(response)
        return response.json()

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code == 429:
            raise RateLimitError("SSI rate limit reached")
        if response.status_code == 404:
            raise SymbolNotFound("SSI symbol not found")
        if 400 <= response.status_code < 500:
            raise ProviderUnavailable(f"SSI client error {response.status_code}")
        if response.status_code >= 500:
            raise ProviderUnavailable(f"SSI server error {response.status_code}")

    def _find_symbol_record(self, payload: Any, symbol: str) -> dict[str, Any]:
        records = self._unwrap_records(payload)
        for record in records:
            record_symbol = first_present(record, ("symbol", "stockSymbol", "code", "ticker"))
            if str(record_symbol or "").upper() == symbol:
                return record
        if len(records) == 1:
            return records[0]
        raise SymbolNotFound(f"SSI symbol not found: {symbol}")

    @staticmethod
    def _unwrap_records(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("data", "items", "result", "rows", "list"):
                nested = payload.get(key)
                if isinstance(nested, list):
                    return [item for item in nested if isinstance(item, dict)]
            return [unwrap_first_record(payload)]
        raise ParserError("SSI returned unsupported payload")

    @staticmethod
    def _parse_record(record: dict[str, Any], symbol: str) -> PriceQuote:
        price = require_decimal(
            first_present(record, ("matchedPrice", "lastPrice", "price", "closePrice", "last")),
            "price",
        )
        if price < Decimal("1000"):
            price *= Decimal("1000")
        metadata = {
            "volume": decimal_or_none(first_present(record, ("nmVolume", "volume", "matchedVolume"))),
            "change_pct": decimal_or_none(first_present(record, ("changePercent", "change_pct", "percentPriceChange"))),
            "high": decimal_or_none(first_present(record, ("highest", "high", "ceilingPrice"))),
            "low": decimal_or_none(first_present(record, ("lowest", "low", "floorPrice"))),
            "open": decimal_or_none(first_present(record, ("open", "openPrice", "refPrice"))),
        }
        return PriceQuote(
            symbol=symbol,
            price=price,
            currency="VND",
            asset_type="stock",
            fetched_at=datetime.now(timezone.utc),
            source="ssi",
            metadata=metadata,
        )
