"""Multi-bank savings rate scraper with skip-on-failure behavior."""
from __future__ import annotations

import importlib
import logging
from collections.abc import Awaitable, Callable

import httpx

from backend.market_data.providers.bank_parsers import BANKS
from backend.market_data.providers.bank_parsers.common import BankRate

logger = logging.getLogger(__name__)

FetchHTML = Callable[[str], Awaitable[str]]

DEFAULT_BANK_URLS: dict[str, str] = {
    key: f"https://example.invalid/{key}/lai-suat" for key in BANKS
}


class BankRatesScraper:
    """Fetch bank-rate pages, delegate parsing, and aggregate successful rates."""

    def __init__(self, *, urls: dict[str, str] | None = None, timeout: float = 5.0, fetch_html: FetchHTML | None = None) -> None:
        self.urls = urls or DEFAULT_BANK_URLS
        self.timeout = timeout
        self._fetch_html = fetch_html

    async def fetch_all(self, bank_keys: list[str] | None = None) -> list[BankRate]:
        rates: list[BankRate] = []
        for bank_key in bank_keys or list(BANKS):
            try:
                html = await self._fetch(bank_key)
                parser = importlib.import_module(f"backend.market_data.providers.bank_parsers.{bank_key}")
                rates.extend(parser.parse_rates(html))
            except Exception as exc:
                logger.warning("Skipping bank rates for %s after parser/fetch error: %s", bank_key, exc)
        return rates

    async def _fetch(self, bank_key: str) -> str:
        if self._fetch_html is not None:
            return await self._fetch_html(bank_key)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(self.urls[bank_key])
        response.raise_for_status()
        return response.text
