from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from backend.market_data.exceptions import ProviderUnavailable
from backend.market_data.normalizer import PriceQuote
from backend.wealth.models.asset import Asset
from backend.wealth.valuation.crypto import (
    value_crypto_holding,
    value_crypto_holdings,
)
from backend.wealth.valuation.gold import value_gold_holding
from backend.wealth.valuation.stock import (
    value_stock_holding,
    value_stock_holdings,
)


def _asset(asset_type: str, extra: dict, current_value=Decimal("8000000")) -> Asset:
    a = Asset()
    a.asset_type = asset_type
    a.name = extra.get("ticker") or extra.get("symbol") or "asset"
    a.extra = extra
    a.initial_value = Decimal("7000000")
    a.current_value = current_value
    return a


def _quote(symbol: str, price: str, asset_type: str, *, is_stale=False) -> PriceQuote:
    return PriceQuote(symbol, Decimal(price), "VND", asset_type, datetime.now(timezone.utc), "test", is_stale=is_stale)


@pytest.mark.asyncio
async def test_stock_valuation_uses_market_price_and_pnl():
    with patch("backend.wealth.valuation.stock.get_stock_quote", AsyncMock(return_value=_quote("VNM", "90000", "stock"))):
        valuation = await value_stock_holding(_asset("stock", {"ticker": "VNM", "quantity": 100, "avg_price": 80000}))

    assert valuation.current_price == Decimal("90000")
    assert valuation.current_value == Decimal("9000000")
    assert valuation.pnl_pct == Decimal("12.500")
    assert valuation.is_stale is False


@pytest.mark.asyncio
async def test_stock_valuation_fallback_uses_user_input_price_and_marks_stale():
    with patch("backend.wealth.valuation.stock.get_stock_quote", AsyncMock(side_effect=ProviderUnavailable("down"))):
        valuation = await value_stock_holding(_asset("stock", {"ticker": "VNM", "quantity": 100, "avg_price": 80000}))

    assert valuation.current_price == Decimal("80000")
    assert valuation.current_value == Decimal("8000000")
    assert valuation.pnl_pct == Decimal("0")
    assert valuation.is_stale is True


@pytest.mark.asyncio
async def test_crypto_valuation_uses_market_price_and_pnl():
    with patch("backend.wealth.valuation.crypto.get_crypto_quote", AsyncMock(return_value=_quote("BTC", "120", "crypto"))):
        valuation = await value_crypto_holding(_asset("crypto", {"symbol": "BTC", "quantity": "2", "avg_price": "100"}))

    assert valuation.current_price == Decimal("120")
    assert valuation.current_value == Decimal("240")
    assert valuation.pnl_pct == Decimal("20.0")


@pytest.mark.asyncio
async def test_crypto_valuation_fallback_uses_current_value_when_avg_missing():
    with patch("backend.wealth.valuation.crypto.get_crypto_quote", AsyncMock(side_effect=ProviderUnavailable("down"))):
        valuation = await value_crypto_holding(_asset("crypto", {"symbol": "ETH", "quantity": "2"}, current_value=Decimal("300")))

    assert valuation.current_price == Decimal("150")
    assert valuation.current_value == Decimal("300")
    assert valuation.is_stale is True


@pytest.mark.asyncio
async def test_zero_cost_basis_keeps_pnl_none():
    with patch("backend.wealth.valuation.stock.get_stock_quote", AsyncMock(return_value=_quote("ABC", "100", "stock"))):
        valuation = await value_stock_holding(_asset("stock", {"ticker": "ABC", "quantity": 1, "avg_price": 0}, current_value=Decimal("0")))

    assert valuation.pnl_pct is None


@pytest.mark.asyncio
async def test_gold_valuation_uses_market_price_and_pnl():
    with patch("backend.wealth.valuation.gold.get_gold_quote", AsyncMock(return_value=_quote("SJC_GOLD", "90000000", "gold"))):
        valuation = await value_gold_holding(_asset("gold", {"type": "SJC", "tael": "2", "avg_price": "80000000"}, current_value=Decimal("160000000")))

    assert valuation.current_price == Decimal("90000000")
    assert valuation.current_value == Decimal("180000000")
    assert valuation.pnl_pct == Decimal("12.500")


@pytest.mark.asyncio
async def test_gold_valuation_fallback_marks_stale():
    with patch("backend.wealth.valuation.gold.get_gold_quote", AsyncMock(side_effect=ProviderUnavailable("down"))):
        valuation = await value_gold_holding(_asset("gold", {"type": "SJC", "weight_gram": "37.5", "avg_price": "80000000"}))

    assert valuation.current_price == Decimal("80000000")
    assert valuation.is_stale is True


# ----- batched crypto valuation (issue #797) ------------------------


@pytest.mark.asyncio
async def test_value_crypto_holdings_batches_single_provider_call():
    # A multi-coin portfolio must hit the provider once, not once per
    # coin. The sequential per-asset path was the dominant contributor
    # to the 10s+ ``query_assets`` reply latency tracked in issue #797.
    btc = _asset("crypto", {"symbol": "BTC", "quantity": "0.5", "avg_price": "1000000000"})
    eth = _asset("crypto", {"symbol": "ETH", "quantity": "2", "avg_price": "80000000"})
    sol = _asset("crypto", {"symbol": "SOL", "quantity": "10", "avg_price": "2000000"})

    quotes = {
        "BTC": _quote("BTC", "2000000000", "crypto"),
        "ETH": _quote("ETH", "100000000", "crypto"),
        "SOL": _quote("SOL", "3000000", "crypto"),
    }
    fetch = AsyncMock(return_value=quotes)
    with patch("backend.wealth.valuation.crypto.get_fast_crypto_quotes", fetch):
        valuations = await value_crypto_holdings([btc, eth, sol])

    assert fetch.await_count == 1
    fetched_symbols = set(fetch.await_args.args[0])
    assert fetched_symbols == {"BTC", "ETH", "SOL"}

    assert valuations[btc].current_value == Decimal("1000000000")
    assert valuations[eth].current_value == Decimal("200000000")
    assert valuations[sol].current_value == Decimal("30000000")
    assert all(not v.is_stale for v in valuations.values())


@pytest.mark.asyncio
async def test_value_crypto_holdings_ignores_non_crypto_assets():
    cash = _asset("cash", {}, current_value=Decimal("50000000"))
    btc = _asset("crypto", {"symbol": "BTC", "quantity": "1", "avg_price": "1000000000"})
    quotes = {"BTC": _quote("BTC", "2000000000", "crypto")}
    with patch(
        "backend.wealth.valuation.crypto.get_fast_crypto_quotes",
        AsyncMock(return_value=quotes),
    ):
        valuations = await value_crypto_holdings([cash, btc])

    assert cash not in valuations
    assert valuations[btc].current_value == Decimal("2000000000")


@pytest.mark.asyncio
async def test_value_crypto_holdings_falls_back_when_batch_raises():
    # Provider failure must not crash the user-facing reply — every
    # asset still gets a valuation, flagged stale, using the stored
    # ``avg_price`` so the displayed number is at least the user's
    # last known reality.
    btc = _asset("crypto", {"symbol": "BTC", "quantity": "0.5", "avg_price": "1000000000"})
    eth = _asset("crypto", {"symbol": "ETH", "quantity": "2", "avg_price": "80000000"})
    with patch(
        "backend.wealth.valuation.crypto.get_fast_crypto_quotes",
        AsyncMock(side_effect=ProviderUnavailable("down")),
    ):
        valuations = await value_crypto_holdings([btc, eth])

    assert valuations[btc].current_price == Decimal("1000000000")
    assert valuations[eth].current_price == Decimal("80000000")
    assert all(v.is_stale for v in valuations.values())


@pytest.mark.asyncio
async def test_value_crypto_holdings_empty_input_skips_provider():
    fetch = AsyncMock(return_value={})
    with patch("backend.wealth.valuation.crypto.get_fast_crypto_quotes", fetch):
        valuations = await value_crypto_holdings([])

    assert valuations == {}
    assert fetch.await_count == 0


# ----- batched stock valuation (issue #797 follow-up) ----------------


@pytest.mark.asyncio
async def test_value_stock_holdings_batches_single_provider_call():
    vnm = _asset("stock", {"ticker": "VNM", "quantity": 100, "avg_price": 80000})
    hpg = _asset("stock", {"ticker": "HPG", "quantity": 200, "avg_price": 25000})
    fpt = _asset("stock", {"ticker": "FPT", "quantity": 50, "avg_price": 120000})
    quotes = {
        "VNM": _quote("VNM", "90000", "stock"),
        "HPG": _quote("HPG", "30000", "stock"),
        "FPT": _quote("FPT", "150000", "stock"),
    }
    fetch = AsyncMock(return_value=quotes)
    with patch("backend.wealth.valuation.stock.get_stock_quotes", fetch):
        valuations = await value_stock_holdings([vnm, hpg, fpt])

    assert fetch.await_count == 1
    fetched = set(fetch.await_args.args[0])
    assert fetched == {"VNM", "HPG", "FPT"}
    assert valuations[vnm].current_value == Decimal("9000000")
    assert valuations[hpg].current_value == Decimal("6000000")
    assert valuations[fpt].current_value == Decimal("7500000")
    assert all(not v.is_stale for v in valuations.values())


@pytest.mark.asyncio
async def test_value_stock_holdings_ignores_non_stock_and_handles_provider_failure():
    cash = _asset("cash", {}, current_value=Decimal("50000000"))
    vnm = _asset("stock", {"ticker": "VNM", "quantity": 100, "avg_price": 80000})
    with patch(
        "backend.wealth.valuation.stock.get_stock_quotes",
        AsyncMock(side_effect=ProviderUnavailable("down")),
    ):
        valuations = await value_stock_holdings([cash, vnm])

    assert cash not in valuations
    assert valuations[vnm].current_price == Decimal("80000")
    assert valuations[vnm].is_stale is True


@pytest.mark.asyncio
async def test_value_stock_holdings_empty_input_skips_provider():
    fetch = AsyncMock(return_value={})
    with patch("backend.wealth.valuation.stock.get_stock_quotes", fetch):
        valuations = await value_stock_holdings([])

    assert valuations == {}
    assert fetch.await_count == 0


@pytest.mark.asyncio
async def test_value_crypto_holdings_missing_symbol_falls_back_per_asset():
    # If the batch comes back without a quote for a given symbol
    # (unknown coin, partial provider response), that asset must still
    # render with its stored ``avg_price`` rather than disappearing
    # from the reply.
    btc = _asset("crypto", {"symbol": "BTC", "quantity": "1", "avg_price": "1000000000"})
    obscure = _asset(
        "crypto", {"symbol": "OBSCURE", "quantity": "5", "avg_price": "10000"}
    )
    quotes = {"BTC": _quote("BTC", "2000000000", "crypto")}
    with patch(
        "backend.wealth.valuation.crypto.get_fast_crypto_quotes",
        AsyncMock(return_value=quotes),
    ):
        valuations = await value_crypto_holdings([btc, obscure])

    assert valuations[btc].is_stale is False
    assert valuations[obscure].is_stale is True
    assert valuations[obscure].current_price == Decimal("10000")
