from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from backend.market_data.exceptions import ParserError
from backend.market_data.providers.base_dispatcher import Dispatcher
from backend.market_data.providers.gold_pnj import PNJGoldProvider
from backend.market_data.providers.gold_sjc import SJCGoldProvider
from backend.tests.test_market_data.fakes import FakeAsyncRedis

FIXTURES = Path(__file__).parents[1] / "fixtures"


def _client(html: str, status: int = 200):
    transport = httpx.MockTransport(lambda request: httpx.Response(status, text=html, request=request))
    return httpx.AsyncClient(transport=transport)


@pytest.mark.asyncio
async def test_sjc_gold_provider_parses_fixture():
    async with _client((FIXTURES / "sjc_sample.html").read_text()) as client:
        quote = await SJCGoldProvider(client=client).fetch_quote("SJC_GOLD")

    assert quote.symbol == "SJC_GOLD"
    assert quote.price == Decimal("90000000")
    assert quote.metadata["buy_price"] == Decimal("88500000")
    assert quote.metadata["sjc_updated_at"] is not None


@pytest.mark.asyncio
async def test_sjc_parser_error_when_table_missing():
    async with _client("<html><body>no table</body></html>") as client:
        with pytest.raises(ParserError):
            await SJCGoldProvider(client=client).fetch_quote("SJC_GOLD")


@pytest.mark.asyncio
async def test_gold_dispatcher_falls_back_to_pnj():
    async with _client("broken") as sjc_client, _client((FIXTURES / "pnj_sample.html").read_text()) as pnj_client:
        dispatcher = Dispatcher(SJCGoldProvider(client=sjc_client), PNJGoldProvider(client=pnj_client), FakeAsyncRedis())
        quote = await dispatcher.fetch_quote("SJC_GOLD")

    assert quote.source == "pnj"
    assert quote.price == Decimal("89900000.0")
