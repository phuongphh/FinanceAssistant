"""Unit tests for ``backend.bot.formatters.briefing_formatter``.

Exercises one branch per wealth level plus the documented edge cases
from issue #69:

- 0 assets → empty state message (no net worth math, no division-by-zero)
- net worth = 0 → empty state (sold everything path)
- change pct = 0 → "no_change" template, never "+0đ (0.0%)"
- output stays under 800 chars on the mobile target

The DB layer is stubbed — we patch ``net_worth_calculator.calculate``
and ``calculate_change`` so the formatter sees fixed inputs.
"""
from __future__ import annotations

import uuid
from datetime import time
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.bot.formatters import briefing_formatter as bf
from backend.bot.formatters.briefing_formatter import (
    MAX_BRIEFING_CHARS,
    BriefingFormatter,
    _signed_money_short,
    _signed_pct,
    _change_emoji,
)
from backend.models.user import User
from backend.wealth.ladder import WealthLevel
from backend.wealth.services.net_worth_calculator import (
    NetWorthBreakdown,
    NetWorthChange,
)


def _make_user(*, name: str = "Minh", **kwargs) -> User:
    u = User()
    u.id = uuid.uuid4()
    u.telegram_id = 999
    u.display_name = name
    u.expense_threshold_micro = 200_000
    u.expense_threshold_major = 2_000_000
    u.briefing_enabled = True
    u.briefing_time = time(7, 0)
    u.monthly_income = kwargs.get("monthly_income")
    return u


def _make_breakdown(total: Decimal, by_type: dict | None = None) -> NetWorthBreakdown:
    by_type = by_type or {"cash": total}
    return NetWorthBreakdown(
        total=total,
        by_type={k: Decimal(v) for k, v in by_type.items()},
        asset_count=len(by_type) if total > 0 else 0,
        largest_asset=("Test", total),
    )


def _make_change(current: Decimal, previous: Decimal) -> NetWorthChange:
    delta = current - previous
    pct = float(delta / previous * 100) if previous > 0 else 0.0
    return NetWorthChange(
        current=current,
        previous=previous,
        change_absolute=delta,
        change_percentage=pct,
        period_label="hôm qua",
    )


# ── Pure helpers ─────────────────────────────────────────────────────


class TestHelpers:
    def test_signed_money_short_positive_adds_plus(self):
        assert _signed_money_short(Decimal("50_000")).startswith("+")

    def test_signed_money_short_negative_keeps_sign(self):
        assert _signed_money_short(Decimal("-100_000")).startswith("-")

    def test_signed_pct_keeps_sign(self):
        assert _signed_pct(1.5) == "+1.5"
        assert _signed_pct(-0.3) == "-0.3"
        assert _signed_pct(0) == "+0.0"

    def test_change_emoji(self):
        assert _change_emoji(Decimal("1")) == "📈"
        assert _change_emoji(Decimal("-1")) == "📉"
        assert _change_emoji(Decimal("0")) == "➖"


# ── Formatter integration ────────────────────────────────────────────


@pytest.mark.asyncio
class TestGenerateForUser:
    def setup_method(self):
        # Force fresh template cache for each test so a content-edit
        # test elsewhere doesn't leak state in.
        bf._load_templates.cache_clear()

    async def _render(self, user, breakdown, change):
        formatter = BriefingFormatter()
        with patch(
            "backend.bot.formatters.briefing_formatter.net_worth_calculator.calculate",
            new=AsyncMock(return_value=breakdown),
        ), patch(
            "backend.bot.formatters.briefing_formatter.net_worth_calculator.calculate_change",
            new=AsyncMock(return_value=change),
        ):
            return await formatter.generate_for_user(MagicMock(), user)

    async def test_starter_includes_net_worth_milestone_and_tip(self):
        user = _make_user()
        breakdown = _make_breakdown(Decimal("10_000_000"))
        change = _make_change(Decimal("10_000_000"), Decimal("9_500_000"))

        result = await self._render(user, breakdown, change)
        assert result.level == WealthLevel.STARTER
        assert result.is_empty_state is False
        assert "Minh" in result.text
        # Money lines render
        assert "10tr" in result.text
        # Milestone block present (mentions Mục tiêu / Mốc)
        assert ("Mốc tiếp theo" in result.text) or ("Mục tiêu" in result.text)
        # Educational tip present (one of the three keywords from the YAML)
        assert "💡" in result.text
        # Storytelling prompt with threshold appended
        assert "200k" in result.text
        # Fits on a phone screen
        assert result.char_count <= MAX_BRIEFING_CHARS

    async def test_young_prof_uses_breakdown_and_action_prompt(self):
        user = _make_user()
        breakdown = _make_breakdown(
            Decimal("100_000_000"),
            {"cash": Decimal("70_000_000"), "stock": Decimal("30_000_000")},
        )
        change = _make_change(Decimal("100_000_000"), Decimal("99_000_000"))

        result = await self._render(user, breakdown, change)
        assert result.level == WealthLevel.YOUNG_PROFESSIONAL
        # Breakdown lines render with both types
        assert "Tiền mặt" in result.text or "💵" in result.text
        assert "Chứng khoán" in result.text or "📈" in result.text
        assert "Phân bổ" in result.text
        assert result.char_count <= MAX_BRIEFING_CHARS

    async def test_mass_affluent_includes_cashflow_section(self):
        user = _make_user(monthly_income=Decimal("30_000_000"))
        breakdown = _make_breakdown(
            Decimal("500_000_000"),
            {"cash": Decimal("200_000_000"), "stock": Decimal("300_000_000")},
        )
        change = _make_change(Decimal("500_000_000"), Decimal("498_000_000"))

        # Mock the expense sum query to return 10tr. AsyncMock's
        # `return_value` is what `await db.execute(...)` resolves to,
        # so configure `.scalar()` on the resolved value.
        result_proxy = MagicMock()
        result_proxy.scalar.return_value = Decimal("10_000_000")
        db = MagicMock()
        db.execute = AsyncMock(return_value=result_proxy)

        formatter = BriefingFormatter()
        with patch(
            "backend.bot.formatters.briefing_formatter.net_worth_calculator.calculate",
            new=AsyncMock(return_value=breakdown),
        ), patch(
            "backend.bot.formatters.briefing_formatter.net_worth_calculator.calculate_change",
            new=AsyncMock(return_value=change),
        ):
            result = await formatter.generate_for_user(db, user)

        assert result.level == WealthLevel.MASS_AFFLUENT
        assert "Dòng tiền" in result.text
        # Saving rate rendered (should be ~67% — 20tr saved on 30tr income)
        assert "%" in result.text
        # Phase 3B placeholder present
        assert "Phase 3B" in result.text or "thị trường" in result.text.lower()

    async def test_hnw_renders_with_performance_placeholder(self):
        user = _make_user(name="Anh Quân")
        breakdown = _make_breakdown(
            Decimal("3_000_000_000"),
            {"real_estate": Decimal("2_000_000_000"), "stock": Decimal("1_000_000_000")},
        )
        change = _make_change(Decimal("3_000_000_000"), Decimal("2_999_000_000"))

        result = await self._render(user, breakdown, change)
        assert result.level == WealthLevel.HIGH_NET_WORTH
        assert "Anh Quân" in result.text
        assert "3 tỷ" in result.text or "3,000,000,000" in result.text
        assert "Phase 3B" in result.text or "Performance" in result.text

    async def test_zero_change_uses_no_change_template(self):
        user = _make_user()
        breakdown = _make_breakdown(Decimal("10_000_000"))
        change = _make_change(Decimal("10_000_000"), Decimal("10_000_000"))

        result = await self._render(user, breakdown, change)
        # Neither "+0đ" nor "0.0%" should appear in the no-change branch.
        assert "+0đ" not in result.text
        assert "0.0%" not in result.text
        assert "Chưa thay đổi" in result.text or "Chưa đổi" in result.text

    async def test_no_assets_returns_empty_state(self):
        user = _make_user()
        breakdown = _make_breakdown(Decimal("0"), by_type={})
        change = _make_change(Decimal("0"), Decimal("0"))

        result = await self._render(user, breakdown, change)
        assert result.is_empty_state is True
        # No net-worth math snuck through
        assert "Tài sản hôm nay" not in result.text
        # CTA present
        assert "Thêm" in result.text or "tài sản" in result.text

    async def test_zero_net_worth_after_selling_falls_through_to_empty_state(self):
        """User with sold-out portfolio (0 net worth, 0 active assets) must
        not crash on percentage divisions and should land on empty state."""
        user = _make_user()
        breakdown = NetWorthBreakdown(
            total=Decimal("0"),
            by_type={},
            asset_count=0,
            largest_asset=(None, Decimal(0)),
        )
        change = _make_change(Decimal("0"), Decimal("0"))

        result = await self._render(user, breakdown, change)
        assert result.is_empty_state is True

    async def test_missing_display_name_falls_back_to_ban(self):
        user = _make_user(name="")
        breakdown = _make_breakdown(Decimal("10_000_000"))
        change = _make_change(Decimal("10_000_000"), Decimal("9_500_000"))

        result = await self._render(user, breakdown, change)
        # User.get_greeting_name() returns "bạn" for empty display_name.
        assert "bạn" in result.text
