from __future__ import annotations

import time
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from backend.market_data.base import BaseProvider
from backend.market_data.cache.cache_keys import health_failures_key, health_open_until_key
from backend.market_data.exceptions import ProviderUnavailable
from backend.market_data.normalizer import PriceQuote
from backend.market_data.providers.base_dispatcher import Dispatcher
from backend.tests.test_market_data.fakes import FakeAsyncRedis


class _FlakyProvider(BaseProvider):
    def __init__(self, name: str, *, fail: bool = False) -> None:
        self.name = name
        self.fail = fail
        self.calls = 0

    @property
    def asset_type(self) -> str:
        return "stock"

    async def fetch_quote(self, symbol: str) -> PriceQuote:
        self.calls += 1
        if self.fail:
            raise ProviderUnavailable(self.name)
        return PriceQuote(symbol, Decimal("100"), "VND", "stock", datetime(2026, 5, 8, tzinfo=timezone.utc), self.name)

    async def fetch_batch(self, symbols: list[str]) -> list[PriceQuote]:
        return [await self.fetch_quote(symbol) for symbol in symbols]


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_five_failures_then_half_open_after_five_minutes():
    redis = FakeAsyncRedis()
    primary = _FlakyProvider("ssi", fail=True)
    secondary = _FlakyProvider("vndirect")
    dispatcher = Dispatcher(primary, secondary, redis)

    for _ in range(5):
        quote = await dispatcher.fetch_quote("VNM")
        assert quote.source == "vndirect"

    open_until = await redis.get(health_open_until_key("ssi"))
    assert open_until is not None
    assert float(open_until) > time.time()

    quote = await dispatcher.fetch_quote("VNM")
    assert quote.source == "vndirect"
    assert primary.calls == 5

    await redis.setex(health_open_until_key("ssi"), 300, str(time.time() - 1))
    primary.fail = False
    quote = await dispatcher.fetch_quote("VNM")

    assert quote.source == "ssi"
    assert await redis.get(health_failures_key("ssi")) is None
    assert await redis.get(health_open_until_key("ssi")) is None
