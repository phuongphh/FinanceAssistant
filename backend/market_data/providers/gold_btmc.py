"""BTMC gold provider — JSON API used as SJC backup.

PNJ's `/site/gia-vang` page is now JS-rendered (Next.js) — server returns
0 tables. BTMC publishes a key-based public JSON endpoint used by their
own Android app, which returns SJC bullion and 24K ring prices in one
call without WAF blocking. This is significantly more durable than
HTML scraping: the API has been stable since at least 2018.

API format (each row keyed by `@row` value, other fields suffixed with it):

    {
      "DataList": {
        "Data": [
          {
            "@row": "1",
            "@name_1": "VÀNG MIẾNG SJC",
            "@buy_1k": "84500000",
            "@sell_1k": "85500000",
            "@row_date_1": "08/05/2026 18:00",
            ...
          },
          {"@row": "2", "@name_2": "VÀNG NHẪN BTMC", ...}
        ]
      }
    }
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


_DEFAULT_URL = (
    "http://api.btmc.vn/api/BTMCAPI/getpricebtmc"
    "?key=3kd8ub1llcg9t45hnoh8hmn7t5kc2v"
)

# BTMC product names → our normalized symbols.
# Order matters: more specific matches go first ("nhẫn ép" before "sjc").
_NAME_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("RING_24K", ("nhẫn", "nhan", "9999", "999.9", "24k")),
    ("SJC_GOLD", ("vàng miếng sjc", "sjc 1l", "vàng sjc", "sjc")),
)


class BTMCGoldProvider(BaseProvider):
    """Fetch and normalize BTMC gold prices via their public JSON endpoint."""

    name = "btmc"

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
        payload = await self._get_json()
        try:
            data = payload["DataList"]["Data"]
        except (KeyError, TypeError) as exc:
            raise ParserError(f"BTMC: unexpected JSON shape: {exc}") from exc
        if not isinstance(data, list) or not data:
            raise ParserError("BTMC: empty data list")
        return data

    async def _get_json(self) -> Any:
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
            raise RateLimitError("BTMC rate limit reached")
        if response.status_code == 404:
            raise SymbolNotFound("BTMC API not found")
        if response.status_code >= 400:
            raise ProviderUnavailable(f"BTMC unavailable: HTTP {response.status_code}")
        try:
            return response.json()
        except Exception as exc:
            raise ParserError(f"BTMC returned non-JSON: {exc}") from exc

    def _build_quote(self, rows: list[dict[str, Any]], symbol: str) -> PriceQuote:
        buy, sell, updated = self._find_row(rows, symbol)
        return PriceQuote(
            symbol=symbol,
            price=sell,
            currency="VND",
            asset_type="gold",
            fetched_at=now_utc(),
            source="btmc",
            metadata={"buy_price": buy, "sell_price": sell, "btmc_updated_at": updated},
        )

    @staticmethod
    def _classify_name(name: str) -> str | None:
        lowered = name.lower()
        for symbol, keywords in _NAME_PATTERNS:
            if any(kw in lowered for kw in keywords):
                return symbol
        return None

    def _find_row(
        self, rows: list[dict[str, Any]], symbol: str
    ) -> tuple[Decimal, Decimal, str | None]:
        if symbol not in {sym for sym, _ in _NAME_PATTERNS}:
            raise SymbolNotFound(f"BTMC: unsupported symbol {symbol}")

        for row in rows:
            row_idx = row.get("@row") or row.get("row")
            if row_idx is None:
                continue
            suffix = str(row_idx)
            name = str(row.get(f"@name_{suffix}") or "")
            if self._classify_name(name) != symbol:
                continue
            buy_raw = row.get(f"@buy_{suffix}k") or row.get(f"@buy_{suffix}")
            sell_raw = row.get(f"@sell_{suffix}k") or row.get(f"@sell_{suffix}")
            updated = row.get(f"@row_date_{suffix}") or row.get("@time_now")
            try:
                buy = self._to_vnd(buy_raw)
                sell = self._to_vnd(sell_raw)
            except (InvalidOperation, ValueError, TypeError) as exc:
                raise ParserError(
                    f"BTMC row {suffix} has unparseable price "
                    f"(buy={buy_raw!r} sell={sell_raw!r}): {exc}"
                ) from exc
            return buy, sell, updated

        raise SymbolNotFound(f"BTMC: no row matching {symbol}")

    @staticmethod
    def _to_vnd(value: Any) -> Decimal:
        if value is None or value == "":
            raise ValueError("missing price")
        text = str(value).replace(",", "").replace(" ", "").strip()
        # BTMC's _Nk fields are already in VND units (e.g. "84500000").
        # The unsuffixed _N fields are in thousands (e.g. "84.500"
        # meaning 84,500,000) — scale up if too small.
        parsed = Decimal(text.replace(".", "")) if "." in text and len(text.split(".")[-1]) == 3 else Decimal(text)
        if parsed < Decimal("1000000"):
            parsed *= Decimal("1000")
        return parsed
