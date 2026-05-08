from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from backend.market_data.exceptions import ProviderUnavailable
from backend.market_data.normalizer import PriceQuote
from backend.wealth.models.asset import Asset
from backend.wealth.valuation.crypto import value_crypto_holding
from backend.wealth.valuation.gold import value_gold_holding
from backend.wealth.valuation.stock import value_stock_holding


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
