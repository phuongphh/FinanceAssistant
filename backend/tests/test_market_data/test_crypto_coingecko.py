from __future__ import annotations

from decimal import Decimal

import httpx
import pytest

from backend.market_data.exceptions import RateLimitError, SymbolNotFound
from backend.market_data.providers.coingecko_symbols import COINGECKO_SYMBOLS
from backend.market_data.providers.crypto_coingecko import CoinGeckoCryptoProvider


@pytest.mark.asyncio
async def test_coingecko_mapping_has_minimum_common_symbols():
    assert len(COINGECKO_SYMBOLS) >= 20
    assert COINGECKO_SYMBOLS["BTC"] == "bitcoin"


@pytest.mark.asyncio
async def test_fetch_quote_returns_vnd_price():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={"bitcoin": {"vnd": 2500000000, "usd": 100000, "vnd_24h_change": 2.5}},
            request=request,
        )
    )
    async with httpx.AsyncClient(base_url="https://example.test", transport=transport) as client:
        quote = await CoinGeckoCryptoProvider(client=client).fetch_quote("BTC")

    assert quote.price == Decimal("2500000000")
    assert quote.currency == "VND"
    assert quote.metadata["coin_id"] == "bitcoin"


@pytest.mark.asyncio
async def test_fetch_batch_uses_one_comma_separated_request():
    seen_ids = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_ids.append(request.url.params["ids"])
        return httpx.Response(
            200,
            json={
                "bitcoin": {"vnd": 1},
                "ethereum": {"vnd": 2},
            },
            request=request,
        )

    async with httpx.AsyncClient(base_url="https://example.test", transport=httpx.MockTransport(handler)) as client:
        quotes = await CoinGeckoCryptoProvider(client=client).fetch_batch(["BTC", "ETH"])

    assert seen_ids == ["bitcoin,ethereum"]
    assert [quote.symbol for quote in quotes] == ["BTC", "ETH"]


@pytest.mark.asyncio
async def test_unknown_symbol_raises_symbol_not_found():
    provider = CoinGeckoCryptoProvider()
    with pytest.raises(SymbolNotFound):
        await provider.fetch_quote("NOPE")


@pytest.mark.asyncio
async def test_429_retries_with_exponential_backoff_then_raises():
    sleeps = []
    transport = httpx.MockTransport(lambda request: httpx.Response(429, json={}, request=request))

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    async with httpx.AsyncClient(base_url="https://example.test", transport=transport) as client:
        with pytest.raises(RateLimitError):
            await CoinGeckoCryptoProvider(client=client, sleep=fake_sleep).fetch_quote("BTC")

    assert sleeps == [1, 2, 4]
