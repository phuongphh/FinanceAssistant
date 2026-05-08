from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from backend.briefing.morning_briefing import render_enriched_morning_briefing
from backend.market_data.cache.price_cache import PriceCache
from backend.market_data.exceptions import ProviderUnavailable
from backend.market_data.normalizer import PriceQuote
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


class _DB:
    def __init__(self, assets: list[Asset]) -> None:
        self.assets = assets
        self.calls = 0

    async def execute(self, stmt):
        self.calls += 1
        if self.calls == 2:
            return _Result(rows=self.assets)
        return _Result(scalar=None)


@pytest.mark.asyncio
async def test_stale_data_flow_shows_stale_banner_when_provider_down():
    user = User(id=uuid.uuid4(), telegram_id=1002)
    assets = [
        Asset(
            user_id=user.id,
            asset_type="cash",
            name="Cash",
            initial_value=Decimal("10000000"),
            current_value=Decimal("10000000"),
            acquired_at=date(2026, 1, 1),
            extra={},
            is_active=True,
        )
    ]
    redis = FakeAsyncRedis()
    cache = PriceCache(redis)
    stale_btc = PriceQuote("BTC", Decimal("500000000"), "VND", "crypto", datetime(2026, 5, 8, tzinfo=timezone.utc), "coingecko")
    await cache.set_last_known(stale_btc)

    async def _provider_down(symbol: str) -> PriceQuote:
        cached = await cache.get_last_known(symbol, "crypto")
        if cached is not None:
            return cached
        raise ProviderUnavailable("coingecko")

    with patch("backend.wealth.services.asset_service.get_user_assets", AsyncMock(return_value=assets)), \
         patch("backend.wealth.services.net_worth_calculator.calculate_historical", AsyncMock(return_value=Decimal("10000000"))), \
         patch("backend.briefing.morning_briefing.get_crypto_quote", side_effect=_provider_down), \
         patch("backend.briefing.morning_briefing.get_gold_quote", AsyncMock(return_value=None)), \
         patch("backend.briefing.morning_briefing.get_relevant_news", AsyncMock(return_value=[])), \
         patch("backend.briefing.morning_briefing.get_best_worst_from_assets", AsyncMock(return_value=(None, None))):
        result = await render_enriched_morning_briefing(_DB(assets), user)

    assert result.is_stale is True
    assert "dữ liệu gần nhất" in result.text
    assert "BTC" in result.text
