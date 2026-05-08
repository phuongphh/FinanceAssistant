"""PNJ Edge API gold provider — preferred primary source.

PNJ's `/site/gia-vang` page is Next.js and renders prices client-side, so HTML
scraping is dead. PNJ exposes a clean JSON endpoint at
`edge-api.pnj.io/ecom-frontend/v1/get-gold-price` that powers the same data,
returning per-product rows keyed by stable `masp` codes (verified
2026-05-08). Schema:

    {
      "data": [
        {"masp": "SJC",  "tensp": "Vàng miếng SJC 999.9", "giamua": 16450, "giaban": 16750},
        {"masp": "N24K", "tensp": "Nhẫn Trơn PNJ 999.9",  "giamua": 16430, "giaban": 16730},
        {"masp": "KB",   ...},
        ...
      ]
    }

Prices are in **thousands of VND per chỉ** (e.g. 16,450 = 16,450,000 VND/chỉ
= 164,500,000 VND/lượng). The scaling constant matches the BTMC provider's
unit normalization so callers see one consistent per-lượng quote.

Wired as the dispatcher's primary because it cleanly separates SJC bullion
(`masp=SJC`) from 24K nhẫn (`masp=N24K`) — BTMC quotes the two at parity
on most days, so PNJ gives more accurate per-product breakdown.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from backend.market_data.base import BaseProvider
from backend.market_data.exceptions import (
    ParserError,
    ProviderUnavailable,
    RateLimitError,
    SymbolNotFound,
)
from backend.market_data.normalizer import PriceQuote
from backend.market_data.providers.gold_common import BROWSER_HEADERS, now_utc


_DEFAULT_URL = "https://edge-api.pnj.io/ecom-frontend/v1/get-gold-price"

# PNJ-Edge `masp` codes mapped to our normalized symbols. Other masp values
# (KB, TL, PNJ, 24K, 999, 9920, 22K, 75) refer to PNJ house brands or lower-
# karat jewelry that don't correspond to canonical SJC bullion / 24K nhẫn.
_SYMBOL_TO_MASP: dict[str, str] = {
    "SJC_GOLD": "SJC",
    "RING_24K": "N24K",
}

# PNJ Edge quotes prices as `int` in thousands of VND per chỉ (1/10 lượng).
# Multiply by 1,000 to get VND per chỉ, then by 10 to convert per-chỉ to
# per-lượng — matches the BTMC provider's unit normalization and the
# handler's "đ/lượng" label.
_THOUSANDS_PER_CHI_TO_VND_PER_LUONG = Decimal(10_000)


class PNJJSONGoldProvider(BaseProvider):
    """Fetch gold prices from PNJ's Edge API."""

    # Distinct from the legacy "pnj" name so the dispatcher's circuit breaker
    # tracks this provider's health independently from the HTML scraper.
    name = "pnj-json"

    def __init__(
        self,
        *,
        url: str = _DEFAULT_URL,
        timeout: float = 5.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.url = url
        self.timeout = timeout
        self._client = client

    @property
    def asset_type(self) -> str:
        return "gold"

    async def fetch_quote(self, symbol: str = "SJC_GOLD") -> PriceQuote:
        symbol = symbol.upper().strip()
        rows = await self._get_rows()
        return self._build_quote(rows, symbol)

    async def fetch_batch(self, symbols: list[str]) -> list[PriceQuote]:
        rows = await self._get_rows()
        return [self._build_quote(rows, symbol.upper().strip()) for symbol in symbols]

    async def _get_rows(self) -> list[dict[str, Any]]:
        if self._client is not None:
            response = await self._client.get(self.url)
        else:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                headers=BROWSER_HEADERS,
                follow_redirects=True,
            ) as client:
                response = await client.get(self.url)
        if response.status_code == 429:
            raise RateLimitError("PNJ Edge rate limit reached")
        if response.status_code == 404:
            raise SymbolNotFound("PNJ Edge endpoint not found")
        if response.status_code >= 400:
            raise ProviderUnavailable(
                f"PNJ Edge unavailable: HTTP {response.status_code}"
            )
        try:
            payload = response.json()
        except Exception as exc:
            preview = response.text[:240].replace("\n", " ").replace("\r", " ")
            raise ParserError(
                f"PNJ Edge returned non-JSON "
                f"(content_type={response.headers.get('content-type', '?')!r} "
                f"len={len(response.text)} preview={preview!r}): {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise ParserError(f"PNJ Edge: top-level is {type(payload).__name__}, expected object")
        data = payload.get("data")
        if not isinstance(data, list) or not data:
            raise ParserError(f"PNJ Edge: missing or empty 'data' (keys: {list(payload.keys())})")
        return data

    def _build_quote(self, rows: list[dict[str, Any]], symbol: str) -> PriceQuote:
        masp = _SYMBOL_TO_MASP.get(symbol)
        if masp is None:
            raise SymbolNotFound(f"PNJ Edge: unsupported symbol {symbol}")

        for row in rows:
            if str(row.get("masp", "")).strip().upper() != masp:
                continue
            buy_raw = row.get("giamua")
            sell_raw = row.get("giaban")
            if buy_raw is None or sell_raw is None:
                raise ParserError(
                    f"PNJ Edge row masp={masp!r} missing giamua/giaban "
                    f"(got keys {list(row.keys())})"
                )
            try:
                buy = Decimal(str(buy_raw)) * _THOUSANDS_PER_CHI_TO_VND_PER_LUONG
                sell = Decimal(str(sell_raw)) * _THOUSANDS_PER_CHI_TO_VND_PER_LUONG
            except (InvalidOperation, ValueError, TypeError) as exc:
                raise ParserError(
                    f"PNJ Edge row masp={masp!r} unparseable price "
                    f"(giamua={buy_raw!r} giaban={sell_raw!r}): {exc}"
                ) from exc
            return PriceQuote(
                symbol=symbol,
                price=sell,
                currency="VND",
                asset_type="gold",
                fetched_at=now_utc(),
                source="pnj-json",
                metadata={
                    "buy_price": buy,
                    "sell_price": sell,
                    "pnj_product": str(row.get("tensp", "")),
                },
            )

        raise SymbolNotFound(f"PNJ Edge: no row with masp={masp!r}")
