from __future__ import annotations

from decimal import Decimal

import httpx
import pytest

from backend.market_data.exceptions import ProviderUnavailable, RateLimitError, SymbolNotFound
from backend.market_data.providers.base_dispatcher import Dispatcher
from backend.market_data.providers.stock_ssi import SSIStockProvider
from backend.market_data.providers.stock_vndirect import VNDIRECTStockProvider
from backend.tests.test_market_data.fakes import FakeAsyncRedis


def _client(status: int, payload):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(status, json=payload, request=request)
    )
    return httpx.AsyncClient(base_url="https://example.test", transport=transport)


@pytest.mark.asyncio
async def test_ssi_success_parses_metadata():
    async with _client(200, {"data": [{"stockSymbol": "VNM", "matchedPrice": 86.4, "nmVolume": 1000, "changePercent": 1.2, "highest": 87, "lowest": 85, "open": 86}]}) as client:
        quote = await SSIStockProvider(client=client).fetch_quote("VNM")

    assert quote.symbol == "VNM"
    assert quote.price == Decimal("86400.0")
    assert quote.metadata["volume"] == Decimal("1000")
    assert quote.metadata["change_pct"] == Decimal("1.2")


@pytest.mark.asyncio
async def test_ssi_404_maps_to_symbol_not_found():
    async with _client(404, {}) as client:
        with pytest.raises(SymbolNotFound):
            await SSIStockProvider(client=client).fetch_quote("BAD")


@pytest.mark.asyncio
async def test_ssi_500_maps_to_provider_unavailable():
    async with _client(500, {}) as client:
        with pytest.raises(ProviderUnavailable):
            await SSIStockProvider(client=client).fetch_quote("VNM")


@pytest.mark.asyncio
async def test_ssi_429_maps_to_rate_limit():
    async with _client(429, {}) as client:
        with pytest.raises(RateLimitError):
            await SSIStockProvider(client=client).fetch_quote("VNM")


@pytest.mark.asyncio
async def test_vndirect_parser_normalizes_schema():
    async with _client(200, {"data": [{"code": "FPT", "close": 123.5, "volume": 99, "pctChange": -0.5, "high": 124, "low": 122, "open": 123}]}) as client:
        quote = await VNDIRECTStockProvider(client=client).fetch_quote("FPT")

    assert quote.symbol == "FPT"
    assert quote.price == Decimal("123500.0")
    assert quote.metadata["high"] == Decimal("124")


@pytest.mark.asyncio
async def test_dispatcher_falls_back_to_vndirect_when_ssi_fails():
    async with _client(500, {}) as ssi_client, _client(200, {"data": [{"code": "VNM", "close": 88}]}) as vnd_client:
        dispatcher = Dispatcher(
            SSIStockProvider(client=ssi_client),
            VNDIRECTStockProvider(client=vnd_client),
            FakeAsyncRedis(),
        )
        quote = await dispatcher.fetch_quote("VNM")

    assert quote.source == "vndirect"
    assert quote.price == Decimal("88000")
