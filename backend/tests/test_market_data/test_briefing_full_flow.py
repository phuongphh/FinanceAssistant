from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from backend.briefing.morning_briefing import render_enriched_morning_briefing
from backend.market_data.base import BaseProvider
from backend.market_data.cache.price_cache import PriceCache
from backend.market_data.normalizer import PriceQuote
from backend.market_data.providers.base_dispatcher import Dispatcher
from backend.models.bank_rate import BankRateSnapshot
from backend.models.market_snapshot import MarketSnapshot
from backend.models.user import User
from backend.tests.test_market_data.fakes import FakeAsyncRedis
from backend.wealth.models.asset import Asset


class _Result:
    def __init__(self, *, rows=None, scalar=None):
        self._rows = rows or []
        self._scalar = scalar

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _BriefingDB:
    def __init__(self, assets: list[Asset]) -> None:
        self.assets = assets
        self.calls = 0
        self.vnindex = MarketSnapshot(
            snapshot_date=date(2026, 5, 8),
            asset_code="VNINDEX",
            asset_type="index",
            price=Decimal("1240.5"),
            change_1d_pct=Decimal("1.2"),
        )
        self.vcb = BankRateSnapshot(
            bank_code="VCB",
            bank_name="Vietcombank",
            tenor_months=12,
            rate_pct=Decimal("4.8"),
            deposit_type="online",
        )

    async def execute(self, stmt):
        self.calls += 1
        if self.calls == 1:
            return _Result(scalar=self.vnindex)
        if self.calls == 2:
            return _Result(rows=self.assets)
        return _Result(scalar=self.vcb.rate_pct)


class _StaticProvider(BaseProvider):
    def __init__(self, name: str, asset_type: str, prices: dict[str, Decimal]) -> None:
        self.name = name
        self._asset_type = asset_type
        self.prices = prices
        self.calls: list[str] = []

    @property
    def asset_type(self) -> str:
        return self._asset_type

    async def fetch_quote(self, symbol: str) -> PriceQuote:
        self.calls.append(symbol.upper())
        return PriceQuote(symbol, self.prices[symbol.upper()], "VND", self.asset_type, datetime(2026, 5, 8, tzinfo=timezone.utc), self.name)

    async def fetch_batch(self, symbols: list[str]) -> list[PriceQuote]:
        return [await self.fetch_quote(symbol) for symbol in symbols]


def _asset(user_id: uuid.UUID, asset_type: str, name: str, initial: str, current: str, extra: dict | None = None) -> Asset:
    return Asset(
        user_id=user_id,
        asset_type=asset_type,
        name=name,
        initial_value=Decimal(initial),
        current_value=Decimal(current),
        acquired_at=date(2026, 1, 1),
        extra=extra or {},
        is_active=True,
    )


@pytest.mark.asyncio
async def test_briefing_full_flow_provider_cache_wealth_and_sections():
    user = User(id=uuid.uuid4(), telegram_id=1001, display_name="An")
    assets = [
        _asset(user.id, "stock", "VNM", "100000", "100000", {"ticker": "VNM", "quantity": "10", "avg_price": "10000"}),
        _asset(user.id, "stock", "FPT", "200000", "200000", {"ticker": "FPT", "quantity": "5", "avg_price": "40000"}),
        _asset(user.id, "stock", "SSI", "150000", "150000", {"ticker": "SSI", "quantity": "15", "avg_price": "10000"}),
        _asset(user.id, "crypto", "BTC", "50000000", "50000000", {"symbol": "BTC", "quantity": "0.1", "avg_price": "500000000"}),
        _asset(user.id, "gold", "SJC", "90000000", "90000000", {"symbol": "SJC_GOLD", "quantity": "1", "avg_price": "90000000"}),
        _asset(user.id, "cash", "Emergency cash", "10000000", "10000000", {"bank_code": "TCB", "rate_pct": "3.9"}),
    ]
    redis = FakeAsyncRedis()
    cache = PriceCache(redis)
    stock_provider = Dispatcher(
        _StaticProvider("ssi", "stock", {"VNM": Decimal("11000"), "FPT": Decimal("42000"), "SSI": Decimal("9000")}),
        _StaticProvider("vndirect", "stock", {}),
        redis,
    )
    crypto_provider = _StaticProvider("coingecko", "crypto", {"BTC": Decimal("550000000")})
    gold_quote = PriceQuote("SJC_GOLD", Decimal("92000000"), "VND", "gold", datetime(2026, 5, 8, tzinfo=timezone.utc), "sjc")

    async def _get_crypto_quote(symbol: str) -> PriceQuote:
        quote = await crypto_provider.fetch_quote(symbol)
        await cache.set(quote)
        await cache.set_last_known(quote)
        return quote

    async def _get_gold_quote(symbol: str = "SJC_GOLD") -> PriceQuote:
        await cache.set(gold_quote)
        await cache.set_last_known(gold_quote)
        return gold_quote

    with patch("backend.wealth.services.asset_service.get_user_assets", AsyncMock(return_value=assets)), \
         patch("backend.wealth.services.net_worth_calculator.calculate_historical", AsyncMock(return_value=Decimal("107000000"))), \
         patch("backend.market_data.client.get_price_cache", return_value=cache), \
         patch("backend.market_data.client.get_stock_provider", return_value=stock_provider), \
         patch("backend.market_data.client.get_crypto_provider", return_value=crypto_provider), \
         patch("backend.briefing.morning_briefing.get_crypto_quote", side_effect=_get_crypto_quote), \
         patch("backend.briefing.morning_briefing.get_gold_quote", side_effect=_get_gold_quote), \
         patch("backend.briefing.morning_briefing.get_relevant_news", AsyncMock(return_value=[])):
        result = await render_enriched_morning_briefing(_BriefingDB(assets), user)

    assert "Chào buổi sáng, An!" in result.text
    assert "Tổng tài sản" in result.text
    assert "Thị trường sáng nay" in result.text
    assert "Danh mục" in result.text
    assert "Top tin liên quan" in result.text
    assert "Gợi ý nhanh" in result.text
    assert "stock" in result.text
    assert "crypto" in result.text
    assert "gold" in result.text
    assert "155tr500" in result.sections["net_worth"]
    assert await redis.get("market_data:stock:VNM") is not None
    assert await redis.get("market_data:crypto:BTC") is not None
    assert result.is_stale is False
