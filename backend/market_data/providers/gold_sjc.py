"""SJC gold scraper provider."""
from __future__ import annotations

import httpx

from backend.market_data.base import BaseProvider
from backend.market_data.exceptions import ProviderUnavailable, RateLimitError, SymbolNotFound
from backend.market_data.normalizer import PriceQuote
from backend.market_data.providers.gold_common import BROWSER_HEADERS, now_utc, parse_gold_table


class SJCGoldProvider(BaseProvider):
    """Fetch and normalize SJC gold prices from the public textContent page."""

    name = "sjc"

    def __init__(self, *, url: str = "https://sjc.com.vn/giavang/textContent.php", timeout: float = 5.0, client: httpx.AsyncClient | None = None) -> None:
        self.url = url
        self.timeout = timeout
        self._client = client

    @property
    def asset_type(self) -> str:
        return "gold"

    async def fetch_quote(self, symbol: str = "SJC_GOLD") -> PriceQuote:
        symbol = symbol.upper().strip()
        html = await self._get_html()
        buy_price, sell_price, updated_at = parse_gold_table(html, symbol=symbol, source_label="SJC")
        return PriceQuote(
            symbol=symbol,
            price=sell_price,
            currency="VND",
            asset_type="gold",
            fetched_at=now_utc(),
            source="sjc",
            metadata={"buy_price": buy_price, "sell_price": sell_price, "sjc_updated_at": updated_at},
        )

    async def fetch_batch(self, symbols: list[str]) -> list[PriceQuote]:
        return [await self.fetch_quote(symbol) for symbol in symbols]

    async def _get_html(self) -> str:
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
            raise RateLimitError("SJC rate limit reached")
        if response.status_code == 404:
            raise SymbolNotFound("SJC gold page not found")
        if response.status_code >= 400:
            raise ProviderUnavailable(f"SJC unavailable: HTTP {response.status_code}")
        return response.text
