"""Base provider contract for market data integrations."""
from __future__ import annotations

from abc import ABC, abstractmethod

from backend.market_data.normalizer import PriceQuote


class BaseProvider(ABC):
    """Common async interface implemented by every market data provider."""

    @abstractmethod
    async def fetch_quote(self, symbol: str) -> PriceQuote:
        """Fetch one normalized quote for ``symbol``."""

    @abstractmethod
    async def fetch_batch(self, symbols: list[str]) -> list[PriceQuote]:
        """Fetch normalized quotes for many symbols."""

    @property
    @abstractmethod
    def asset_type(self) -> str:
        """Asset type produced by this provider (stock, crypto, gold, ...)."""
