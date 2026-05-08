from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest

from backend.market_data.base import BaseProvider
from backend.market_data.cache.price_cache import PriceCache
from backend.market_data.exceptions import ProviderUnavailable
from backend.market_data.normalizer import PriceQuote
from backend.market_data.providers.base_dispatcher import Dispatcher
from backend.tests.test_market_data.fakes import FakeAsyncRedis
from backend.wealth.models.asset import Asset
from backend.wealth.valuation.stock import value_stock_holding


class _Provider(BaseProvider):
    def __init__(self, name: str, *, price: Decimal | None = None, fail: bool = False) -> None:
        self.name = name
        self.price = price
        self.fail = fail
        self.calls = 0

    @property
    def asset_type(self) -> str:
        return "stock"

    async def fetch_quote(self, symbol: str) -> PriceQuote:
        self.calls += 1
        if self.fail:
            raise ProviderUnavailable(self.name)
        return PriceQuote(symbol, self.price or Decimal("0"), "VND", "stock", datetime(2026, 5, 8, tzinfo=timezone.utc), self.name)

    async def fetch_batch(self, symbols: list[str]) -> list[PriceQuote]:
        return [await self.fetch_quote(symbol) for symbol in symbols]


@pytest.mark.asyncio
async def test_provider_fallback_uses_vndirect_and_wealth_valuation_is_correct():
    redis = FakeAsyncRedis()
    cache = PriceCache(redis)
    ssi = _Provider("ssi", fail=True)
    vndirect = _Provider("vndirect", price=Decimal("1200"))
    dispatcher = Dispatcher(ssi, vndirect, redis)
    asset = Asset(
        user_id=uuid.uuid4(),
        asset_type="stock",
        name="VNM",
        initial_value=Decimal("10000"),
        current_value=Decimal("10000"),
        acquired_at=date(2026, 1, 1),
        extra={"ticker": "VNM", "quantity": "10", "avg_price": "1000"},
        is_active=True,
    )

    with patch("backend.market_data.client.get_price_cache", return_value=cache), \
         patch("backend.market_data.client.get_stock_provider", return_value=dispatcher):
        valuation = await value_stock_holding(asset)

    assert ssi.calls == 1
    assert vndirect.calls == 1
    assert valuation.current_price == Decimal("1200")
    assert valuation.current_value == Decimal("12000")
    assert valuation.pnl_pct == Decimal("20.0")
    assert await redis.get("market_data:stock:VNM:last_known") is not None
