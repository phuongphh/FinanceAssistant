from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from backend.market_data.exceptions import ParserError, SymbolNotFound
from backend.market_data.providers.base_dispatcher import Dispatcher
from backend.market_data.providers.gold_btmc import BTMCGoldProvider
from backend.market_data.providers.gold_pnj import PNJGoldProvider
from backend.market_data.providers.gold_sjc import SJCGoldProvider
from backend.market_data.providers import gold_btmc, gold_pnj, gold_sjc
from backend.market_data.providers.gold_common import BROWSER_HEADERS
from backend.tests.test_market_data.fakes import FakeAsyncRedis

FIXTURES = Path(__file__).parents[1] / "fixtures"


def _client(html: str, status: int = 200):
    transport = httpx.MockTransport(lambda request: httpx.Response(status, text=html, request=request))
    return httpx.AsyncClient(transport=transport)


def _json_client(json_text: str, status: int = 200):
    def _handler(request):
        return httpx.Response(
            status,
            text=json_text,
            headers={"content-type": "application/json"},
            request=request,
        )

    transport = httpx.MockTransport(_handler)
    return httpx.AsyncClient(transport=transport)


def _xml_client(xml_text: str, status: int = 200):
    def _handler(request):
        return httpx.Response(
            status,
            text=xml_text,
            headers={"content-type": "application/xml; charset=utf-8"},
            request=request,
        )

    transport = httpx.MockTransport(_handler)
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


@pytest.mark.parametrize(
    "module, provider_cls",
    [(gold_sjc, SJCGoldProvider), (gold_pnj, PNJGoldProvider), (gold_btmc, BTMCGoldProvider)],
)
@pytest.mark.asyncio
async def test_gold_provider_sends_browser_headers_and_follows_redirects(monkeypatch, module, provider_cls):
    """Regression: scrape-style providers must send a real browser fingerprint.

    Default python-httpx UA is rejected at WAF level by all three sources;
    redirects must be followed so the parser sees the final page body.
    """
    captured: dict = {}

    class _RecordingClient:
        def __init__(self, *args, **kwargs):
            captured["init_kwargs"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def get(self, url):
            captured["url"] = url
            if provider_cls is SJCGoldProvider:
                body = (FIXTURES / "sjc_sample.html").read_text()
                return httpx.Response(200, text=body, request=httpx.Request("GET", url))
            if provider_cls is PNJGoldProvider:
                body = (FIXTURES / "pnj_sample.html").read_text()
                return httpx.Response(200, text=body, request=httpx.Request("GET", url))
            body = (FIXTURES / "btmc_sample.json").read_text()
            return httpx.Response(
                200,
                text=body,
                headers={"content-type": "application/json"},
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr(module.httpx, "AsyncClient", _RecordingClient)

    quote = await provider_cls().fetch_quote("SJC_GOLD")

    assert quote.symbol == "SJC_GOLD"
    assert captured["init_kwargs"]["headers"] == BROWSER_HEADERS
    assert captured["init_kwargs"]["follow_redirects"] is True
    assert "User-Agent" in BROWSER_HEADERS
    assert "Mozilla" in BROWSER_HEADERS["User-Agent"]


@pytest.mark.asyncio
async def test_btmc_parses_sjc_bullion_from_fixture():
    fixture = (FIXTURES / "btmc_sample.json").read_text()
    async with _json_client(fixture) as client:
        quote = await BTMCGoldProvider(client=client).fetch_quote("SJC_GOLD")

    assert quote.symbol == "SJC_GOLD"
    assert quote.source == "btmc"
    assert quote.price == Decimal("85500000")
    assert quote.metadata["buy_price"] == Decimal("84500000")
    assert quote.metadata["btmc_updated_at"] == "08/05/2026 18:00"


@pytest.mark.asyncio
async def test_btmc_parses_24k_ring_from_fixture():
    fixture = (FIXTURES / "btmc_sample.json").read_text()
    async with _json_client(fixture) as client:
        quote = await BTMCGoldProvider(client=client).fetch_quote("RING_24K")

    assert quote.symbol == "RING_24K"
    assert quote.source == "btmc"
    assert quote.price == Decimal("79300000")
    assert quote.metadata["buy_price"] == Decimal("78200000")


@pytest.mark.asyncio
async def test_btmc_parses_shape_b_without_at_row_field():
    """Regression for review on PR #308: BTMC also returns rows without `@row`,
    using abbreviated prefixes (`@n_N`, `@pb_N`, `@ps_N`). The parser must
    infer the suffix from row keys and try alternate prefixes; otherwise an
    SJC outage falls through to SymbolNotFound and users see "chưa có dữ liệu".
    """
    fixture = (FIXTURES / "btmc_shape_b_sample.json").read_text()
    async with _json_client(fixture) as client:
        sjc_quote = await BTMCGoldProvider(client=client).fetch_quote("SJC_GOLD")
        ring_quote = await BTMCGoldProvider(client=client).fetch_quote("RING_24K")

    assert sjc_quote.symbol == "SJC_GOLD"
    assert sjc_quote.source == "btmc"
    assert sjc_quote.price == Decimal("85500000")
    assert sjc_quote.metadata["buy_price"] == Decimal("84500000")

    assert ring_quote.symbol == "RING_24K"
    assert ring_quote.price == Decimal("79300000")
    assert ring_quote.metadata["buy_price"] == Decimal("78200000")


@pytest.mark.asyncio
async def test_btmc_parses_xml_payload_for_sjc_bullion():
    """Regression: BTMC's public endpoint serves XML rather than JSON
    (confirmed by bakeoff diag 2026-05-08: content-type=application/xml,
    len=181915, contained 'BẠC THỎI 2025' and 'VÀNG'). The provider must
    detect the format and parse XML, otherwise SJC outage falls through
    to ParserError and users see "chưa có dữ liệu".
    """
    fixture = (FIXTURES / "btmc_sample.xml").read_text()
    async with _xml_client(fixture) as client:
        sjc_quote = await BTMCGoldProvider(client=client).fetch_quote("SJC_GOLD")
        ring_quote = await BTMCGoldProvider(client=client).fetch_quote("RING_24K")

    assert sjc_quote.source == "btmc"
    assert sjc_quote.price == Decimal("85500000")
    assert sjc_quote.metadata["buy_price"] == Decimal("84500000")
    assert sjc_quote.metadata["btmc_updated_at"] == "08/05/2026 19:00"

    assert ring_quote.price == Decimal("79300000")
    assert ring_quote.metadata["buy_price"] == Decimal("78200000")


@pytest.mark.asyncio
async def test_btmc_xml_ignores_silver_rows():
    """The XML fixture contains a 'BẠC THỎI 2025' (silver bullion) row;
    it must not be misclassified as gold and the gold-only request must
    still resolve to the SJC bullion row.
    """
    fixture = (FIXTURES / "btmc_sample.xml").read_text()
    async with _xml_client(fixture) as client:
        quote = await BTMCGoldProvider(client=client).fetch_quote("SJC_GOLD")
    assert quote.metadata["buy_price"] == Decimal("84500000")


@pytest.mark.asyncio
async def test_btmc_raises_when_no_matching_row():
    fixture = '{"DataList":{"Data":[{"@row":"1","@name_1":"VÀNG TRANG SỨC 18K","@buy_1k":"55000000","@sell_1k":"56000000"}]}}'
    async with _json_client(fixture) as client:
        with pytest.raises(SymbolNotFound):
            await BTMCGoldProvider(client=client).fetch_quote("SJC_GOLD")


@pytest.mark.asyncio
async def test_btmc_raises_parser_error_on_unexpected_shape():
    async with _json_client('{"unexpected":"shape"}') as client:
        with pytest.raises(ParserError):
            await BTMCGoldProvider(client=client).fetch_quote("SJC_GOLD")


@pytest.mark.asyncio
async def test_gold_dispatcher_falls_back_to_btmc_on_sjc_failure():
    """When SJC raises (e.g. 403), dispatcher should serve the BTMC quote."""
    fixture = (FIXTURES / "btmc_sample.json").read_text()
    async with _client("forbidden", status=403) as sjc_client, _json_client(fixture) as btmc_client:
        dispatcher = Dispatcher(
            SJCGoldProvider(client=sjc_client),
            BTMCGoldProvider(client=btmc_client),
            FakeAsyncRedis(),
        )
        quote = await dispatcher.fetch_quote("SJC_GOLD")

    assert quote.source == "btmc"
    assert quote.price == Decimal("85500000")
