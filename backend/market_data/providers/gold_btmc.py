"""BTMC gold provider — JSON API used as SJC backup.

PNJ's `/site/gia-vang` page is now JS-rendered (Next.js) — server returns
0 tables. BTMC publishes a key-based public JSON endpoint used by their
own Android app, which returns SJC bullion and 24K ring prices in one
call without WAF blocking. This is significantly more durable than
HTML scraping: the API has been stable since at least 2018.

API format — BTMC ships two flavours of row in the same `DataList.Data`,
both keyed by a numeric suffix that varies per row. The parser must
infer the suffix from the row's keys and try both naming conventions:

  Shape A (with `@row` and full prefixes):

      {
        "@row": "1",
        "@name_1": "VÀNG MIẾNG SJC",
        "@buy_1k": "84500000",
        "@sell_1k": "85500000",
        "@row_date_1": "08/05/2026 18:00"
      }

  Shape B (no `@row`, abbreviated prefixes):

      {
        "@n_7": "VÀNG MIẾNG SJC",
        "@pb_7": "84500000",
        "@ps_7": "85500000"
      }
"""
from __future__ import annotations

import re
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
# Order matters: more specific matches go first ("nhẫn" before "sjc")
# so a name like "VÀNG NHẪN SJC" classifies as RING_24K, not SJC bullion.
_NAME_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("RING_24K", ("nhẫn", "nhan", "9999", "999.9", "24k")),
    ("SJC_GOLD", ("vàng miếng sjc", "sjc 1l", "vàng sjc", "sjc")),
)

# Alternate prefixes for the same logical fields; tried in order until a
# non-empty value is found. `@name_N` (Shape A) before `@n_N` (Shape B).
_NAME_PREFIXES = ("name", "n")
_BUY_PREFIXES = ("buy", "pb")
_SELL_PREFIXES = ("sell", "ps")

# Match `@<word>_<digits>` or `@<word>_<digits>k` keys to extract the suffix.
_SUFFIX_KEY_RE = re.compile(r"^@[A-Za-z_]+_(\d+)k?$")


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
            preview = response.text[:240].replace("\n", " ").replace("\r", " ")
            raise ParserError(
                f"BTMC returned non-JSON "
                f"(content_type={response.headers.get('content-type', '?')!r} "
                f"len={len(response.text)} preview={preview!r}): {exc}"
            ) from exc

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

    @staticmethod
    def _row_suffix(row: dict[str, Any]) -> str | None:
        """Return the numeric suffix shared by this row's `@*_N` keys.

        Shape A rows expose it directly via `@row`. Shape B rows omit
        `@row`, so we count suffixes across all `@<word>_N(k)?` keys
        and return the most common one.
        """
        explicit = row.get("@row") or row.get("row")
        if explicit is not None and str(explicit).strip():
            return str(explicit).strip()

        counts: dict[str, int] = {}
        for key in row:
            if not isinstance(key, str):
                continue
            match = _SUFFIX_KEY_RE.match(key)
            if match:
                suffix = match.group(1)
                counts[suffix] = counts.get(suffix, 0) + 1
        if not counts:
            return None
        return max(counts.items(), key=lambda item: item[1])[0]

    @staticmethod
    def _row_field(
        row: dict[str, Any],
        suffix: str,
        prefixes: tuple[str, ...],
        *,
        prefer_k: bool = False,
    ) -> Any:
        """Look up `@<prefix>_<suffix>` (or `@<prefix>_<suffix>k`) for any
        prefix in `prefixes`. The first non-empty hit wins.

        `prefer_k=True` is for price fields, where `@buy_1k` (raw VND
        integer) is more reliable than `@buy_1` (often in thousands).
        """
        for prefix in prefixes:
            candidates = (
                (f"@{prefix}_{suffix}k", f"@{prefix}_{suffix}")
                if prefer_k
                else (f"@{prefix}_{suffix}", f"@{prefix}_{suffix}k")
            )
            for key in candidates:
                value = row.get(key)
                if value not in (None, ""):
                    return value
        return None

    def _find_row(
        self, rows: list[dict[str, Any]], symbol: str
    ) -> tuple[Decimal, Decimal, str | None]:
        if symbol not in {sym for sym, _ in _NAME_PATTERNS}:
            raise SymbolNotFound(f"BTMC: unsupported symbol {symbol}")

        for row in rows:
            suffix = self._row_suffix(row)
            if suffix is None:
                continue
            name = self._row_field(row, suffix, _NAME_PREFIXES)
            if not name or self._classify_name(str(name)) != symbol:
                continue
            buy_raw = self._row_field(row, suffix, _BUY_PREFIXES, prefer_k=True)
            sell_raw = self._row_field(row, suffix, _SELL_PREFIXES, prefer_k=True)
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
