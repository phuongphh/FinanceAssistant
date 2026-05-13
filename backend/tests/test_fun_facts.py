"""Unit tests for the weekly fun-fact generator (Phase 2, Issue #42).

Focus
-----
- YAML integrity: every documented fact template is present.
- Coffee / grab / delivery / weekend / biggest_category render with real
  user data (no hardcoded example strings).
- Empty-data path returns None instead of a generic "fallback" message
  with no numbers — silent is better than dishonest.
- Vietnamese money formatting reuses Phase 1 helpers (45,000đ / 1.5tr).
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.bot.personality import fun_facts
from backend.bot.personality.fun_facts import _ExpenseRow
from backend.models.user import User


def _row(
    amount: float = 100_000,
    merchant: str | None = None,
    note: str | None = None,
    category: str = "food",
    expense_date: date | None = None,
) -> _ExpenseRow:
    return _ExpenseRow(
        amount=amount,
        merchant=merchant,
        note=note,
        category=category,
        expense_date=expense_date or date(2026, 4, 20),
    )


def _make_user(name: str = "Minh") -> User:
    u = User()
    u.id = uuid.uuid4()
    u.telegram_id = 222
    u.display_name = name
    u.onboarding_skipped = False
    u.onboarding_completed_at = None
    return u


def _scalar_result(value):
    r = MagicMock()
    r.scalar_one.return_value = value
    r.scalar_one_or_none.return_value = value
    return r


def _rows_result(rows):
    r = MagicMock()
    r.all.return_value = rows
    return r


class TestYamlIntegrity:
    def test_all_expected_template_keys_present(self):
        fun_facts.reload_templates_for_tests()
        tmpl = fun_facts._load_templates()
        expected = {
            "coffee_equivalent", "grab_count", "food_delivery_count",
            "weekend_vs_weekday", "biggest_category", "new_merchant",
            "saving_projection", "day_of_month_pattern",
        }
        for key in expected:
            assert key in tmpl, f"Missing fun-fact template: {key}"
            assert "template" in tmpl[key]

    def test_category_insights_cover_all_codes(self):
        """Each category code we show as top must have an insight string."""
        fun_facts.reload_templates_for_tests()
        insights = fun_facts._load_templates().get("category_insights") or {}
        for code in (
            "food", "transport", "shopping", "entertainment", "health",
            "education", "utility", "housing", "saving", "investment",
            "gift", "transfer", "other",
        ):
            assert code in insights


class TestRendering:
    def test_coffee_renders_cup_count_and_savings(self):
        fun_facts.reload_templates_for_tests()
        user = _make_user("Lan")
        fact = fun_facts._render_coffee(user, spend=1_100_000)
        assert "Lan" in fact.text
        assert "1,100,000đ" in fact.text
        # 1.1M / 55k ≈ 20 cups
        assert "20" in fact.text
        assert fact.key == "coffee_equivalent"

    def test_grab_renders_count_total_avg(self):
        fun_facts.reload_templates_for_tests()
        user = _make_user("Hoa")
        fact = fun_facts._render_grab(user, count=8, total=480_000)
        assert "Hoa" in fact.text
        assert "8" in fact.text
        assert "480,000đ" in fact.text
        assert "60,000đ" in fact.text  # avg per trip

    def test_weekend_renders_ratio(self):
        fun_facts.reload_templates_for_tests()
        user = _make_user("Phu")
        fact = fun_facts._render_weekend(
            user, weekend_avg=450_000, weekday_avg=200_000
        )
        assert "2.2" in fact.text or "2.3" in fact.text  # ~2.25x

    def test_biggest_category_renders_vietnamese_label(self):
        fun_facts.reload_templates_for_tests()
        user = _make_user("Minh")
        fact = fun_facts._render_biggest_category(
            user, "food", amount=1_200_000, pct=38.0,
        )
        assert "Ăn uống" in fact.text
        assert "1,200,000đ" in fact.text
        assert "38" in fact.text


@pytest.mark.asyncio
class TestGenerateForUser:
    async def test_no_recent_data_returns_none(self):
        """User with zero expenses in 14 days should not receive a generic fact."""
        user = _make_user()
        with patch(
            "backend.bot.personality.fun_facts._fetch_expenses",
            new_callable=AsyncMock, return_value=[],
        ):
            out = await fun_facts.generate_for_user(
                MagicMock(), user, today=date(2026, 4, 23),
            )
        assert out is None

    async def test_coffee_wins_priority_over_biggest_category(self):
        """Specific funny fact beats generic top-category fallback."""
        user = _make_user("Tuan")
        today = date(2026, 4, 23)
        # Enough coffee spend to trip the 500k threshold, and enough
        # recent activity (last 14d) to pass the fast-fail check.
        rows = [
            _row(amount=300_000, merchant="Highlands Coffee", expense_date=today - timedelta(days=2)),
            _row(amount=300_000, merchant="Starbucks", expense_date=today - timedelta(days=5)),
            _row(amount=300_000, merchant="Phuc Long", expense_date=today - timedelta(days=10)),
        ]
        with patch(
            "backend.bot.personality.fun_facts._fetch_expenses",
            new_callable=AsyncMock, return_value=rows,
        ):
            out = await fun_facts.generate_for_user(
                MagicMock(), user, today=today,
            )
        assert out is not None
        assert out.key == "coffee_equivalent"
        assert "Tuan" in out.text

    async def test_falls_back_to_biggest_category(self):
        """If no specific fact qualifies, return the biggest-category
        fact — but only if there IS a top category."""
        user = _make_user("Minh")
        today = date(2026, 4, 23)
        # No coffee, no grab, no delivery — just regular transport spend
        # in the last 7 days so biggest_category kicks in.
        rows = [
            _row(amount=150_000, category="transport", expense_date=today - timedelta(days=1)),
            _row(amount=150_000, category="transport", expense_date=today - timedelta(days=3)),
            _row(amount=50_000, category="food", expense_date=today - timedelta(days=2)),
        ]
        with patch(
            "backend.bot.personality.fun_facts._fetch_expenses",
            new_callable=AsyncMock, return_value=rows,
        ):
            out = await fun_facts.generate_for_user(
                MagicMock(), user, today=today,
            )
        assert out is not None
        assert out.key == "biggest_category"
        assert "Di chuyển" in out.text

    async def test_normalizes_legacy_category_code(self):
        """Top category with legacy code 'food_drink' should map to 'food'."""
        user = _make_user("Hoa")
        today = date(2026, 4, 23)
        rows = [
            _row(amount=200_000, category="food_drink", expense_date=today - timedelta(days=1)),
            _row(amount=100_000, category="food", expense_date=today - timedelta(days=2)),
        ]
        with patch(
            "backend.bot.personality.fun_facts._fetch_expenses",
            new_callable=AsyncMock, return_value=rows,
        ):
            out = await fun_facts.generate_for_user(
                MagicMock(), user, today=today,
            )
        assert out is not None
        assert out.key == "biggest_category"
        # The two rows should collapse into a single "Ăn uống" category.
        assert "Ăn uống" in out.text
        assert "300,000đ" in out.text


class TestPureAggregations:
    def test_coffee_spend_sums_coffee_merchants(self):
        rows = [
            _row(amount=200_000, merchant="Highlands"),
            _row(amount=50_000, merchant="7-Eleven"),
            _row(amount=100_000, merchant="The Coffee House"),
        ]
        assert fun_facts._coffee_spend(rows) == 300_000

    def test_grab_excludes_grabfood(self):
        rows = [
            _row(amount=80_000, merchant="Grab"),
            _row(amount=150_000, merchant="GrabFood"),  # should NOT count
            _row(amount=70_000, merchant="Grab ride HCM"),
        ]
        count, total = fun_facts._grab_stats(rows)
        assert count == 2
        assert total == 150_000

    def test_weekend_weekday_averages_by_day(self):
        rows = [
            # Sat 2026-04-18 — two purchases, should count as ONE day.
            _row(amount=500_000, expense_date=date(2026, 4, 18)),
            _row(amount=500_000, expense_date=date(2026, 4, 18)),
            # Sun 2026-04-19 — one purchase.
            _row(amount=300_000, expense_date=date(2026, 4, 19)),
            # Mon 2026-04-20.
            _row(amount=200_000, expense_date=date(2026, 4, 20)),
        ]
        we_avg, wd_avg = fun_facts._weekend_weekday_avg(rows)
        assert we_avg == 650_000  # (1,000,000 + 300,000) / 2
        assert wd_avg == 200_000
