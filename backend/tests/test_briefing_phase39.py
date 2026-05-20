from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

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


def test_greeting_stays_plain_text_for_entity_renderer():
    user = User()
    user.display_name = "An <VIP>"

    from backend.briefing.morning_briefing import _greeting_line

    line = _greeting_line(user)

    assert line.startswith("🌤️ Chào buổi sáng")
    assert "An <VIP>" in line


# ── Regression: Gợi ý nhanh insight lines ─────────────────────────────
#
# Before this fix the briefing rendered absurd best/worst lines like
# "Tốt nhất: FPT +29099900.0%; yếu nhất: TIỀN MẶT -4569.0%" whenever cost
# basis was corrupted or cash drifted from its onboarding snapshot.
# These tests pin the new contract: skip silently when no data, collapse
# to a single-asset line when only one performer is eligible, and use
# the localized templates from briefing.yaml (not hardcoded strings).


async def _render_with_performers(performers, breakdown=None, change=None):
    """Render briefing with given (best, worst) — other dependencies stubbed."""
    user = User()
    user.id = uuid.uuid4()
    user.telegram_id = 1
    user.display_name = "Test"
    if breakdown is None:
        breakdown = NetWorthBreakdown(
            total=Decimal("100000000"),
            by_type={"stock": Decimal("60000000"), "cash": Decimal("40000000")},
            asset_count=2,
        )
    if change is None:
        change = NetWorthChange(
            Decimal("100000000"), Decimal("99000000"), Decimal("1000000"), 1.0, "hôm qua",
        )

    with patch("backend.briefing.morning_briefing.net_worth_calculator.calculate", AsyncMock(return_value=breakdown)), \
         patch("backend.briefing.morning_briefing.net_worth_calculator.calculate_change", AsyncMock(return_value=change)), \
         patch("backend.briefing.morning_briefing.net_worth_calculator.get_daily_movers", AsyncMock(return_value=[])), \
         patch("backend.briefing.morning_briefing.get_crypto_quote", AsyncMock(return_value=_quote("BTC", "100", "crypto"))), \
         patch("backend.briefing.morning_briefing.get_gold_quote", AsyncMock(return_value=_quote("SJC_GOLD", "90000000", "gold"))), \
         patch("backend.briefing.morning_briefing.get_relevant_news", AsyncMock(return_value=[])), \
         patch("backend.briefing.morning_briefing.get_best_worst_from_assets", AsyncMock(return_value=performers)):
        return await render_enriched_morning_briefing(_DB(), user)


@pytest.mark.asyncio
async def test_briefing_omits_best_worst_line_when_no_eligible_performer():
    """get_best_worst_from_assets returns (None, None) when every holding
    is cash/real_estate or has corrupt cost basis. The Gợi ý nhanh section
    still renders, but no performance line is included."""
    result = await _render_with_performers((None, None))
    assert "Gợi ý nhanh" in result.text
    assert "Tốt nhất" not in result.text
    assert "yếu nhất" not in result.text
    assert "Hiệu suất:" not in result.text
    assert "Đa dạng hóa" in result.text


@pytest.mark.asyncio
async def test_briefing_renders_pair_line_for_distinct_best_and_worst():
    best_id = uuid.uuid4()
    worst_id = uuid.uuid4()
    performers = (
        {"asset_id": best_id, "symbol": "VNM", "asset_type": "stock", "current_value": Decimal("100"), "cost_basis_value": Decimal("90"), "return_pct": Decimal("11")},
        {"asset_id": worst_id, "symbol": "MWG", "asset_type": "stock", "current_value": Decimal("80"), "cost_basis_value": Decimal("100"), "return_pct": Decimal("-20")},
    )
    result = await _render_with_performers(performers)
    assert "Tốt nhất: VNM +11.0%" in result.text
    assert "yếu nhất: MWG -20.0%" in result.text


@pytest.mark.asyncio
async def test_briefing_collapses_to_single_line_when_best_equals_worst():
    """Single eligible holding: best and worst share asset_id. Showing
    'Tốt nhất: X +5%; yếu nhất: X +5%' reads as a bug to users, so we
    collapse to a 'Hiệu suất:' line instead."""
    only_id = uuid.uuid4()
    performer = {
        "asset_id": only_id,
        "symbol": "VNM",
        "asset_type": "stock",
        "current_value": Decimal("100"),
        "cost_basis_value": Decimal("95"),
        "return_pct": Decimal("5.3"),
    }
    result = await _render_with_performers((performer, performer))
    assert "Hiệu suất: VNM +5.3%" in result.text
    assert "Tốt nhất" not in result.text
    assert "yếu nhất" not in result.text


@pytest.mark.asyncio
async def test_briefing_diversification_line_always_rendered():
    result = await _render_with_performers((None, None))
    assert "Đa dạng hóa:" in result.text
    assert "/100" in result.text
