from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from backend.market_data.cache.cache_keys import last_known_key, quote_key
from backend.market_data.cache.price_cache import PriceCache
from backend.market_data.normalizer import PriceQuote
from backend.tests.test_market_data.fakes import FakeAsyncRedis


def _quote(symbol: str = "VNM", asset_type: str = "stock") -> PriceQuote:
    return PriceQuote(
        symbol=symbol,
        price=Decimal("86400"),
        currency="VND",
        asset_type=asset_type,
        fetched_at=datetime(2026, 5, 8, 9, 30, tzinfo=timezone.utc),
        source="ssi",
    )


@pytest.mark.asyncio
async def test_set_and_get_use_standard_key_and_ttl():
    redis = FakeAsyncRedis()
    cache = PriceCache(redis)
    quote = _quote()

    await cache.set(quote)
    restored = await cache.get(quote_key("stock", "VNM"))

    assert restored == quote
    assert quote_key("stock", "VNM") in redis.expires


@pytest.mark.asyncio
async def test_get_returns_none_after_expiry():
    redis = FakeAsyncRedis()
    cache = PriceCache(redis)
    key = quote_key("stock", "VNM")
    await redis.setex(key, -1, _quote().to_json())

    assert await cache.get(key) is None


@pytest.mark.asyncio
async def test_last_known_has_no_ttl_and_is_marked_stale_on_read():
    redis = FakeAsyncRedis()
    cache = PriceCache(redis)
    quote = _quote()

    await cache.set_last_known(quote)
    restored = await cache.get_last_known("VNM", "stock")

    assert restored is not None
    assert restored.symbol == "VNM"
    assert restored.is_stale is True
    assert last_known_key("stock", "VNM") not in redis.expires


@pytest.mark.asyncio
async def test_flush_asset_type_deletes_matching_keys_only():
    redis = FakeAsyncRedis()
    cache = PriceCache(redis)
    await cache.set(_quote("VNM", "stock"))
    await cache.set_last_known(_quote("VNM", "stock"))
    await cache.set(_quote("BTC", "crypto"))

    deleted = await cache.flush_asset_type("stock")

    assert deleted == 2
    assert await redis.get(quote_key("stock", "VNM")) is None
    assert await redis.get(quote_key("crypto", "BTC")) is not None
