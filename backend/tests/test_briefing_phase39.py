from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.briefing.morning_briefing import render_enriched_morning_briefing
from backend.market_data.normalizer import PriceQuote
from backend.models.user import User
from backend.wealth.services.net_worth_calculator import NetWorthBreakdown, NetWorthChange


class _Result:
    def __init__(self, rows=None, scalar=None):
        self.rows = rows or []
        self._scalar = scalar

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return self

    def all(self):
        return self.rows


class _DB:
    async def execute(self, stmt):
        return _Result([])


def _quote(symbol: str, price: str, asset_type: str, *, stale=False):
    return PriceQuote(symbol, Decimal(price), "VND", asset_type, datetime.now(timezone.utc), "test", is_stale=stale)


@pytest.mark.asyncio
async def test_enriched_briefing_renders_five_sections_and_stale_footer():
    user = User()
    user.id = uuid.uuid4()
    user.telegram_id = 123
    user.display_name = "Minh"
    breakdown = NetWorthBreakdown(total=Decimal("100000000"), by_type={"stock": Decimal("60000000"), "cash": Decimal("40000000")}, asset_count=2)
    change = NetWorthChange(Decimal("100000000"), Decimal("99000000"), Decimal("1000000"), 1.0, "hôm qua")

    with patch("backend.briefing.morning_briefing.net_worth_calculator.calculate", AsyncMock(return_value=breakdown)), \
         patch("backend.briefing.morning_briefing.net_worth_calculator.calculate_change", AsyncMock(return_value=change)), \
         patch("backend.briefing.morning_briefing.get_crypto_quote", AsyncMock(return_value=_quote("BTC", "100", "crypto", stale=True))), \
         patch("backend.briefing.morning_briefing.get_gold_quote", AsyncMock(return_value=_quote("SJC_GOLD", "90000000", "gold"))), \
         patch("backend.briefing.morning_briefing.get_relevant_news", AsyncMock(return_value=[])), \
         patch("backend.briefing.morning_briefing.get_best_worst_from_assets", AsyncMock(return_value=(None, None))):
        result = await render_enriched_morning_briefing(_DB(), user)

    assert "Chào buổi sáng, Minh!" in result.text
    assert "Tổng tài sản" in result.text
    assert "Thị trường sáng nay" in result.text
    assert "Danh mục" in result.text
    assert "Top tin liên quan" in result.text
    assert "Gợi ý nhanh" in result.text
    assert "dữ liệu gần nhất" in result.text
    assert result.is_stale is True


def test_greeting_uses_configured_telegram_custom_emoji():
    user = User()
    user.display_name = "An <VIP>"
    settings = MagicMock(telegram_morning_custom_emoji_id='sunrise"id')

    with patch("backend.briefing.morning_briefing.get_settings", return_value=settings):
        from backend.briefing.morning_briefing import _greeting_line

        line = _greeting_line(user)

    assert '<tg-emoji emoji-id="sunrise&quot;id">🌅</tg-emoji>' in line
    assert "An &lt;VIP&gt;" in line
