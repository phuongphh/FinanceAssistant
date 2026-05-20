from __future__ import annotations

from decimal import Decimal

import pytest

from backend.market_data.exceptions import SymbolNotFound
from backend.market_data.providers.stock_stooq import StooqStockProvider


class _Resp:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code


class _Client:
    def __init__(self, text: str, status_code: int = 200):
        self._resp = _Resp(text, status_code)

    async def get(self, path: str, params: dict[str, str]):
        return self._resp


@pytest.mark.asyncio
async def test_fetch_quote_parses_usd_price():
    csv = "Symbol,Date,Time,Open,High,Low,Close,Volume\nNVDA.US,2026-05-20,22:00:00,100,120,99,118.5,123456\n"
    provider = StooqStockProvider(client=_Client(csv))

    quote = await provider.fetch_quote("nvda")

    assert quote.symbol == "NVDA"
    assert quote.price == Decimal("118.5")
    assert quote.currency == "USD"
    assert quote.source == "stooq"


@pytest.mark.asyncio
async def test_fetch_quote_not_found_raises():
    csv = "Symbol,Date,Time,Open,High,Low,Close,Volume\nNVDA.US,2026-05-20,22:00:00,100,120,99,N/D,123456\n"
    provider = StooqStockProvider(client=_Client(csv))

    with pytest.raises(SymbolNotFound):
        await provider.fetch_quote("nvda")
