from __future__ import annotations

from datetime import date, datetime, timezone
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
    return PriceQuote(
        symbol, Decimal("10"), "VND", asset_type, datetime.now(timezone.utc), "test"
    )


@pytest.mark.asyncio
async def test_stock_updater_always_refreshes_vnindex_without_held_symbols():
    redis = FakeAsyncRedis()
    provider = MagicMock()
    provider.fetch_batch = AsyncMock(return_value=[_quote("VNINDEX", "stock")])
    with (
        patch.object(
            stock_updater, "get_session_factory", return_value=_session_factory([])
        ),
        patch.object(stock_updater, "get_stock_provider", return_value=provider),
        patch.object(stock_updater, "get_price_cache", return_value=PriceCache(redis)),
    ):
        metrics = await stock_updater.update_all_held_stocks()

    provider.fetch_batch.assert_awaited_once_with(["VNINDEX"])
    assert metrics["symbols_attempted"] == 1
    assert metrics["symbols_succeeded"] == 1
    assert await redis.get("market_data:stock:VNINDEX") is not None
    assert await redis.get("market_data:stock:VNINDEX:last_known") is not None


@pytest.mark.asyncio
async def test_stock_updater_fetches_distinct_symbols_and_writes_cache():
    redis = FakeAsyncRedis()
    provider = MagicMock()
    provider.fetch_batch = AsyncMock(return_value=[_quote("VNM", "stock")])
    with (
        patch.object(
            stock_updater,
            "get_session_factory",
            return_value=_session_factory([{"ticker": "VNM"}, {"ticker": "vnm"}]),
        ),
        patch.object(stock_updater, "get_stock_provider", return_value=provider),
        patch.object(stock_updater, "get_price_cache", return_value=PriceCache(redis)),
        patch.object(
            stock_updater, "_latest_snapshot_quotes", AsyncMock(return_value={})
        ),
    ):
        metrics = await stock_updater.update_all_held_stocks()

    provider.fetch_batch.assert_awaited_once_with(["VNINDEX", "VNM"])
    assert metrics["symbols_attempted"] == 2
    assert metrics["symbols_succeeded"] == 1
    assert await redis.get("market_data:stock:VNM") is not None
    assert await redis.get("market_data:stock:VNM:last_known") is not None


@pytest.mark.asyncio
async def test_stock_updater_uses_snapshot_when_all_providers_fail():
    redis = FakeAsyncRedis()
    provider = MagicMock()
    provider.fetch_batch = AsyncMock(side_effect=RuntimeError("providers down"))
    fallback = _quote("VNINDEX", "stock").mark_stale()

    with (
        patch.object(
            stock_updater, "get_session_factory", return_value=_session_factory([])
        ),
        patch.object(stock_updater, "get_stock_provider", return_value=provider),
        patch.object(stock_updater, "get_price_cache", return_value=PriceCache(redis)),
        patch.object(
            stock_updater,
            "_latest_snapshot_quotes",
            AsyncMock(return_value={"VNINDEX": fallback}),
        ) as load_snapshots,
    ):
        metrics = await stock_updater.update_all_held_stocks()

    load_snapshots.assert_awaited_once()
    assert metrics["symbols_succeeded"] == 1
    assert metrics["snapshot_fallbacks"] == 1
    assert (await PriceCache(redis).get("market_data:stock:VNINDEX")).is_stale is True
    assert await redis.get("market_data:stock:VNINDEX:last_known") is not None


@pytest.mark.asyncio
async def test_stock_updater_fills_partial_batch_without_overwriting_live_quote():
    redis = FakeAsyncRedis()
    live = _quote("VNM", "stock")
    provider = MagicMock()
    provider.fetch_batch = AsyncMock(return_value=[live])
    fallback = _quote("VNINDEX", "stock").mark_stale()

    with (
        patch.object(
            stock_updater,
            "get_session_factory",
            return_value=_session_factory([{"ticker": "VNM"}]),
        ),
        patch.object(stock_updater, "get_stock_provider", return_value=provider),
        patch.object(stock_updater, "get_price_cache", return_value=PriceCache(redis)),
        patch.object(
            stock_updater,
            "_latest_snapshot_quotes",
            AsyncMock(return_value={"VNINDEX": fallback}),
        ) as load_snapshots,
    ):
        metrics = await stock_updater.update_all_held_stocks()

    assert load_snapshots.await_args.args[1] == ["VNINDEX"]
    assert metrics["symbols_succeeded"] == 2
    assert metrics["snapshot_fallbacks"] == 1
    assert (await PriceCache(redis).get("market_data:stock:VNM")).is_stale is False


@pytest.mark.asyncio
async def test_latest_snapshot_quotes_uses_newest_row_and_preserves_metadata():
    created_at = datetime(2026, 8, 7, 18, tzinfo=timezone.utc)
    newest = MagicMock(
        asset_code="VNINDEX",
        price=Decimal("1768.06"),
        change_1d_pct=Decimal("0.19"),
        extra_data={"change": "3.42", "volume": 123},
        snapshot_date=date(2026, 8, 8),
        created_at=created_at,
    )
    older = MagicMock(
        asset_code="VNINDEX",
        price=Decimal("1700"),
        change_1d_pct=Decimal("-1"),
        extra_data={},
        snapshot_date=date(2026, 8, 7),
        created_at=created_at,
    )

    quotes = await stock_updater._latest_snapshot_quotes(
        _DB([newest, older]), ["VNINDEX"]
    )

    quote = quotes["VNINDEX"]
    assert quote.price == Decimal("1768.06")
    assert quote.fetched_at == created_at
    assert quote.source == "market_snapshot"
    assert quote.metadata["change_pct"] == Decimal("0.19")
    assert quote.metadata["snapshot_date"] == "2026-08-08"
    assert quote.is_stale is True


@pytest.mark.asyncio
async def test_crypto_updater_fetches_distinct_symbols_and_writes_cache():
    redis = FakeAsyncRedis()
    provider = MagicMock()
    provider.fetch_batch = AsyncMock(return_value=[_quote("BTC", "crypto")])
    with (
        patch.object(
            crypto_updater,
            "get_session_factory",
            return_value=_session_factory([{"symbol": "BTC"}]),
        ),
        patch.object(crypto_updater, "get_crypto_provider", return_value=provider),
        patch.object(crypto_updater, "get_price_cache", return_value=PriceCache(redis)),
    ):
        metrics = await crypto_updater.update_all_held_crypto()

    provider.fetch_batch.assert_awaited_once_with(["BTC"])
    assert metrics["symbols_attempted"] == 1
    assert metrics["symbols_succeeded"] == 1
    assert await redis.get("market_data:crypto:BTC") is not None
