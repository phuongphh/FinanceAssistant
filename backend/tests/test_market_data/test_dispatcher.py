from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from backend.market_data.base import BaseProvider
from backend.market_data.cache.cache_keys import (
    health_failures_key,
    health_open_until_key,
)
from backend.market_data.exceptions import ProviderUnavailable
from backend.market_data.normalizer import PriceQuote
from backend.market_data.providers.base_dispatcher import Dispatcher
from backend.tests.test_market_data.fakes import FakeAsyncRedis


class ProviderStub(BaseProvider):
    def __init__(self, name: str, *, fail_times: int = 0) -> None:
        self.name = name
        self.fail_times = fail_times
        self.calls = 0
        self.batch_calls = 0

    @property
    def asset_type(self) -> str:
        return "stock"

    async def fetch_quote(self, symbol: str) -> PriceQuote:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise ProviderUnavailable(self.name)
        return PriceQuote(
            symbol=symbol,
            price=Decimal("100"),
            currency="VND",
            asset_type="stock",
            fetched_at=datetime(2026, 5, 8, tzinfo=timezone.utc),
            source=self.name,
        )

    async def fetch_batch(self, symbols: list[str]) -> list[PriceQuote]:
        self.batch_calls += 1
        return [await self.fetch_quote(symbol) for symbol in symbols]


@pytest.mark.asyncio
async def test_closed_circuit_uses_primary_provider():
    redis = FakeAsyncRedis()
    primary = ProviderStub("ssi")
    secondary = ProviderStub("vndirect")
    dispatcher = Dispatcher(primary, secondary, redis)

    quote = await dispatcher.fetch_quote("VNM")

    assert quote.source == "ssi"
    assert primary.calls == 1
    assert secondary.calls == 0


@pytest.mark.asyncio
async def test_primary_failure_falls_back_and_opens_after_five_failures():
    redis = FakeAsyncRedis()
    primary = ProviderStub("ssi", fail_times=5)
    secondary = ProviderStub("vndirect")
    dispatcher = Dispatcher(primary, secondary, redis)

    for _ in range(5):
        quote = await dispatcher.fetch_quote("VNM")
        assert quote.source == "vndirect"

    assert await redis.get(health_failures_key("ssi")) == "5"
    assert await redis.get(health_open_until_key("ssi")) is not None


@pytest.mark.asyncio
async def test_open_circuit_skips_primary_and_uses_secondary():
    redis = FakeAsyncRedis()
    primary = ProviderStub("ssi")
    secondary = ProviderStub("vndirect")
    await redis.setex(health_open_until_key("ssi"), 300, str(time.time() + 300))
    dispatcher = Dispatcher(primary, secondary, redis)

    quote = await dispatcher.fetch_quote("VNM")

    assert quote.source == "vndirect"
    assert primary.calls == 0
    assert secondary.calls == 1


@pytest.mark.asyncio
async def test_half_open_success_closes_circuit():
    redis = FakeAsyncRedis()
    primary = ProviderStub("ssi")
    secondary = ProviderStub("vndirect")
    await redis.set(health_failures_key("ssi"), "5")
    await redis.setex(health_open_until_key("ssi"), 300, str(time.time() - 1))
    dispatcher = Dispatcher(primary, secondary, redis)

    quote = await dispatcher.fetch_quote("VNM")

    assert quote.source == "ssi"
    assert await redis.get(health_failures_key("ssi")) is None
    assert await redis.get(health_open_until_key("ssi")) is None


@pytest.mark.asyncio
async def test_timeout_is_retryable_and_falls_back():
    class SlowProvider(ProviderStub):
        async def fetch_quote(self, symbol: str) -> PriceQuote:
            self.calls += 1
            await asyncio.sleep(0.05)
            return await super().fetch_quote(symbol)

    redis = FakeAsyncRedis()
    primary = SlowProvider("ssi")
    secondary = ProviderStub("vndirect")
    dispatcher = Dispatcher(primary, secondary, redis, timeout=0.001)

    quote = await dispatcher.fetch_quote("VNM")

    assert quote.source == "vndirect"
    assert await redis.get(health_failures_key("ssi")) == "1"


@pytest.mark.asyncio
async def test_open_secondary_circuit_is_skipped_immediately():
    redis = FakeAsyncRedis()
    primary = ProviderStub("ssi")
    secondary = ProviderStub("vndirect")
    await redis.setex(health_open_until_key("ssi"), 300, str(time.time() + 300))
    await redis.setex(health_open_until_key("vndirect"), 300, str(time.time() + 300))
    dispatcher = Dispatcher(primary, secondary, redis)

    with pytest.raises(ProviderUnavailable):
        await dispatcher.fetch_quote("VNM")

    assert primary.batch_calls == 0
    assert primary.calls == 0
    assert secondary.batch_calls == 0
    assert secondary.calls == 0


@pytest.mark.asyncio
async def test_fetch_batch_uses_provider_batch_once():
    redis = FakeAsyncRedis()
    primary = ProviderStub("ssi")
    secondary = ProviderStub("vndirect")
    dispatcher = Dispatcher(primary, secondary, redis)

    quotes = await dispatcher.fetch_batch(["VNM", "FPT", "HPG"])

    assert [quote.symbol for quote in quotes] == ["VNM", "FPT", "HPG"]
    assert primary.batch_calls == 1
    assert primary.calls == 3
    assert secondary.batch_calls == 0
    assert secondary.calls == 0


class BatchProviderStub(BaseProvider):
    """Provider returning a configurable subset of requested symbols per batch.

    ``returns`` lists which requested symbols the provider answers with; a
    missing or empty entry models a 200-but-empty / shape-drifted response
    that raises no exception.
    """

    def __init__(self, name: str, returns: set[str] | None) -> None:
        self.name = name
        self.returns = returns
        self.batch_calls = 0
        self.calls = 0

    @property
    def asset_type(self) -> str:
        return "stock"

    async def fetch_quote(self, symbol: str) -> PriceQuote:
        self.calls += 1
        return PriceQuote(
            symbol=symbol,
            price=Decimal("100"),
            currency="VND",
            asset_type="stock",
            fetched_at=datetime(2026, 5, 8, tzinfo=timezone.utc),
            source=self.name,
        )

    async def fetch_batch(self, symbols: list[str]) -> list[PriceQuote]:
        self.batch_calls += 1
        allowed = self.returns if self.returns is not None else set(symbols)
        return [
            await self.fetch_quote(symbol) for symbol in symbols if symbol in allowed
        ]


@pytest.mark.asyncio
async def test_empty_primary_batch_falls_back_to_secondary():
    redis = FakeAsyncRedis()
    primary = BatchProviderStub("vndirect", returns=set())  # 200-but-empty
    secondary = BatchProviderStub("ssi", returns={"VNM", "FPT"})
    dispatcher = Dispatcher(primary, secondary, redis)

    quotes = await dispatcher.fetch_batch(["VNM", "FPT"])

    assert sorted(quote.symbol for quote in quotes) == ["FPT", "VNM"]
    assert all(quote.source == "ssi" for quote in quotes)
    assert secondary.batch_calls == 1
    # empty-but-OK primary batch must count as a failure, not a success reset
    assert await redis.get(health_failures_key("vndirect")) == "1"


@pytest.mark.asyncio
async def test_partial_primary_batch_fills_gap_from_secondary():
    redis = FakeAsyncRedis()
    primary = BatchProviderStub("vndirect", returns={"VNM"})
    secondary = BatchProviderStub("ssi", returns={"FPT", "HPG"})
    dispatcher = Dispatcher(primary, secondary, redis)

    quotes = await dispatcher.fetch_batch(["VNM", "FPT", "HPG"])

    by_symbol = {quote.symbol: quote.source for quote in quotes}
    assert by_symbol == {"VNM": "vndirect", "FPT": "ssi", "HPG": "ssi"}
    assert primary.batch_calls == 1
    assert secondary.batch_calls == 1


@pytest.mark.asyncio
async def test_partial_primary_batch_kept_when_secondary_fails():
    redis = FakeAsyncRedis()
    primary = BatchProviderStub("vndirect", returns={"VNM"})
    secondary = ProviderStub("ssi", fail_times=99)
    dispatcher = Dispatcher(primary, secondary, redis)

    quotes = await dispatcher.fetch_batch(["VNM", "FPT"])

    assert [quote.symbol for quote in quotes] == ["VNM"]
    assert quotes[0].source == "vndirect"


@pytest.mark.asyncio
async def test_fetch_batch_skips_open_secondary_circuit():
    redis = FakeAsyncRedis()
    primary = ProviderStub("ssi")
    secondary = ProviderStub("vndirect")
    await redis.setex(health_open_until_key("ssi"), 300, str(time.time() + 300))
    await redis.setex(health_open_until_key("vndirect"), 300, str(time.time() + 300))
    dispatcher = Dispatcher(primary, secondary, redis)

    with pytest.raises(ProviderUnavailable):
        await dispatcher.fetch_batch(["VNM", "FPT", "HPG"])

    assert primary.batch_calls == 0
    assert primary.calls == 0
    assert secondary.batch_calls == 0
    assert secondary.calls == 0
