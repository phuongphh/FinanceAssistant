"""Stooq provider for US/international stock & ETF quotes (no API key)."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from decimal import Decimal
from io import StringIO

import httpx

from backend.market_data.base import BaseProvider
from backend.market_data.exceptions import ParserError, ProviderUnavailable, RateLimitError, SymbolNotFound
from backend.market_data.normalizer import PriceQuote


class StooqStockProvider(BaseProvider):
    name = "stooq"

    def __init__(
        self,
        *,
        base_url: str = "https://stooq.com",
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
        norm = symbol.upper().strip()
        payload = await self._get_csv(norm)
        return self._parse_quote(norm, payload)

    async def fetch_batch(self, symbols: list[str]) -> list[PriceQuote]:
        out: list[PriceQuote] = []
        for symbol in symbols:
            clean = symbol.strip()
            if not clean:
                continue
            out.append(await self.fetch_quote(clean))
        return out

    async def _get_csv(self, symbol: str) -> str:
        params = {"s": f"{symbol.lower()}.us", "i": "d"}

        async def request(client: httpx.AsyncClient) -> httpx.Response:
            return await client.get("/q/l/", params=params)

        if self._client is not None:
            response = await request(self._client)
        else:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
                response = await request(client)
        self._raise_for_status(response)
        return response.text

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code == 429:
            raise RateLimitError("Stooq rate limit reached")
        if response.status_code == 404:
            raise SymbolNotFound("Stooq symbol not found")
        if 400 <= response.status_code < 500:
            raise ProviderUnavailable(f"Stooq client error {response.status_code}")
        if response.status_code >= 500:
            raise ProviderUnavailable(f"Stooq server error {response.status_code}")

    @staticmethod
    def _parse_quote(symbol: str, payload: str) -> PriceQuote:
        reader = csv.DictReader(StringIO(payload))
        row = next(reader, None)
        if row is None:
            raise ParserError("Stooq returned empty CSV payload")
        close = str(row.get("Close", "")).strip()
        if not close or close in {"N/D", "-"}:
            raise SymbolNotFound(f"Stooq symbol not found: {symbol}")
        try:
            price = Decimal(close)
        except Exception as exc:  # pragma: no cover - defensive
            raise ParserError(f"Invalid Stooq close price: {close}") from exc
        return PriceQuote(
            symbol=symbol,
            price=price,
            currency="USD",
            asset_type="stock",
            fetched_at=datetime.now(timezone.utc),
            source="stooq",
            metadata={
                "open": str(row.get("Open", "")).strip() or None,
                "high": str(row.get("High", "")).strip() or None,
                "low": str(row.get("Low", "")).strip() or None,
                "volume": str(row.get("Volume", "")).strip() or None,
            },
        )
