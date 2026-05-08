from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.market_data.cache.price_cache import PriceCache
from backend.market_data.jobs import crypto_updater, stock_updater
from backend.market_data.normalizer import PriceQuote
from backend.tests.test_market_data.fakes import FakeAsyncRedis


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _DB:
    def __init__(self, rows):
        self.rows = rows

    async def execute(self, stmt):
        return _Result(self.rows)


class _SessionCtx:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _session_factory(rows):
    return lambda: _SessionCtx(_DB(rows))


def _quote(symbol: str, asset_type: str) -> PriceQuote:
    return PriceQuote(symbol, Decimal("10"), "VND", asset_type, datetime.now(timezone.utc), "test")


@pytest.mark.asyncio
async def test_stock_updater_noops_when_no_symbols():
    with patch.object(stock_updater, "get_session_factory", return_value=_session_factory([])):
        metrics = await stock_updater.update_all_held_stocks()

    assert metrics["symbols_attempted"] == 0
    assert metrics["symbols_succeeded"] == 0


@pytest.mark.asyncio
async def test_stock_updater_fetches_distinct_symbols_and_writes_cache():
    redis = FakeAsyncRedis()
    provider = MagicMock()
    provider.fetch_batch = AsyncMock(return_value=[_quote("VNM", "stock")])
    with patch.object(stock_updater, "get_session_factory", return_value=_session_factory([{"ticker": "VNM"}, {"ticker": "vnm"}])), patch.object(stock_updater, "get_stock_provider", return_value=provider), patch.object(stock_updater, "get_price_cache", return_value=PriceCache(redis)):
        metrics = await stock_updater.update_all_held_stocks()

    provider.fetch_batch.assert_awaited_once_with(["VNM"])
    assert metrics["symbols_attempted"] == 1
    assert metrics["symbols_succeeded"] == 1
    assert await redis.get("market_data:stock:VNM") is not None
    assert await redis.get("market_data:stock:VNM:last_known") is not None


@pytest.mark.asyncio
async def test_crypto_updater_fetches_distinct_symbols_and_writes_cache():
    redis = FakeAsyncRedis()
    provider = MagicMock()
    provider.fetch_batch = AsyncMock(return_value=[_quote("BTC", "crypto")])
    with patch.object(crypto_updater, "get_session_factory", return_value=_session_factory([{"symbol": "BTC"}])), patch.object(crypto_updater, "get_crypto_provider", return_value=provider), patch.object(crypto_updater, "get_price_cache", return_value=PriceCache(redis)):
        metrics = await crypto_updater.update_all_held_crypto()

    provider.fetch_batch.assert_awaited_once_with(["BTC"])
    assert metrics["symbols_attempted"] == 1
    assert metrics["symbols_succeeded"] == 1
    assert await redis.get("market_data:crypto:BTC") is not None
