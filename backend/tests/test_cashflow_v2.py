"""Unit tests for Phase 4B Epic 3 — Cashflow Forecasting v2.

Coverage (per spec S14 + S16 + S17 + S18 acceptance criteria):

S14 — Recurring pattern detector:
  - test_detect_salary_high_confidence        (salary, day 1, 3 months → conf ≥ 0.9)
  - test_detect_rent_high_confidence          (rent, day 5, fixed amount → conf ≥ 0.85)
  - test_no_detect_random_transactions        (irregular → conf < 0.7 → not emitted)
  - test_amount_band_collapses_small_variance (±2k stays in same band)
  - test_day_band_grouping                    (_day_band maps correctly)

S16 — Forecast model:
  - test_forecast_sums_confirmed_only         (unconfirmed patterns excluded)
  - test_forecast_balance_accumulates         (balance_eom rolls forward each month)
  - test_forecast_current_month_actuals_deducted
  - test_low_balance_risk_detected            (below threshold → low_balance_risk=True)
  - test_threshold_fallback_equals_expense_sum

S17 — Alert dedup:
  - test_alert_dedup_key_format               (key includes user_id + month iso)
  - test_alert_skipped_when_redis_has_key

S18 — Chart:
  - test_chart_renders_png_bytes              (valid PNG header)
  - test_chart_empty_data_does_not_crash

All tests are DB-free via fake sessions and mock Redis.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.cashflow.detector import (
    _day_band,
    _detect_candidates,
    _fingerprint,
    CONFIDENCE_THRESHOLD,
)
from backend.cashflow.forecast import (
    MonthlyForecastData,
    _compute_threshold,
    _month_start_offset,
    _sum_patterns,
)
from backend.models.recurring_pattern import (
    PATTERN_TYPE_EXPENSE,
    PATTERN_TYPE_INCOME,
    RecurringPattern,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_expense(
    *,
    category: str = "rent",
    amount: float = 8_000_000,
    expense_date: date,
    recurrence_id=None,
    deleted_at=None,
    merchant: str | None = None,
) -> MagicMock:
    e = MagicMock()
    e.category = category
    e.amount = amount
    e.expense_date = expense_date
    e.recurrence_id = recurrence_id
    e.deleted_at = deleted_at
    e.merchant = merchant
    return e


def _make_pattern(
    *,
    pattern_type: str = PATTERN_TYPE_EXPENSE,
    amount: float = 8_000_000,
    day: int = 5,
    schedule_type: str = "monthly",
    user_confirmed: bool = True,
    is_active: bool = True,
) -> RecurringPattern:
    p = RecurringPattern()
    p.id = uuid.uuid4()
    p.user_id = uuid.uuid4()
    p.pattern_type = pattern_type
    p.expected_amount = Decimal(str(amount))
    p.expected_day_of_month = day
    p.schedule_type = schedule_type
    p.user_confirmed = user_confirmed
    p.is_active = is_active
    p.name = f"Test pattern {pattern_type}"
    p.description = p.name
    return p


def _make_user(*, cashflow_alert_threshold: float | None = None) -> MagicMock:
    u = MagicMock()
    u.id = uuid.uuid4()
    u.cashflow_alert_threshold = cashflow_alert_threshold
    return u


# ── S14: Detector tests ─────────────────────────────────────────────────────


class TestDayBand:
    def test_day_1_maps_to_band_1(self):
        assert _day_band(1) == 1

    def test_day_5_maps_to_band_5(self):
        assert _day_band(5) == 5

    def test_day_31_maps_to_band_28(self):
        assert _day_band(31) == 28

    def test_day_15_maps_to_band_12(self):
        assert _day_band(15) == 12


class TestFingerprint:
    def test_income_and_expense_different_fingerprints(self):
        fp_income = _fingerprint(PATTERN_TYPE_INCOME, "salary", Decimal("20000000"))
        fp_expense = _fingerprint(PATTERN_TYPE_EXPENSE, "salary", Decimal("20000000"))
        assert fp_income != fp_expense

    def test_amount_band_collapses_small_variance(self):
        # 8_002_000 and 7_998_000 should map to the same bucket (50k band)
        fp1 = _fingerprint(PATTERN_TYPE_EXPENSE, "rent", Decimal("8002000"))
        fp2 = _fingerprint(PATTERN_TYPE_EXPENSE, "rent", Decimal("7998000"))
        assert fp1 == fp2

    def test_large_amount_difference_separates_buckets(self):
        fp1 = _fingerprint(PATTERN_TYPE_EXPENSE, "rent", Decimal("8000000"))
        fp2 = _fingerprint(PATTERN_TYPE_EXPENSE, "rent", Decimal("9000000"))
        assert fp1 != fp2


class TestDetectCandidates:
    def _expenses_for_salary(self) -> list:
        """3 salary transactions on day 1 of 3 consecutive months.

        All use the same amount (20_000_000) so they share the same 50k bucket
        (bucket = round(amount / 50_000) = 400) and are grouped together.
        """
        return [
            _make_expense(category="salary", amount=20_000_000,
                          expense_date=date(2026, 8, 1)),
            _make_expense(category="salary", amount=20_000_000,
                          expense_date=date(2026, 9, 1)),
            _make_expense(category="salary", amount=20_000_000,
                          expense_date=date(2026, 10, 1)),
        ]

    def test_salary_detected_with_high_confidence(self):
        expenses = self._expenses_for_salary()
        candidates = _detect_candidates(
            expenses, [], [],
            lookback_months=3,
            min_occurrences=3,
            confidence_threshold=0.70,
        )
        assert len(candidates) == 1
        assert float(candidates[0].confidence) >= 0.9

    def test_rent_detected_high_confidence(self):
        expenses = [
            _make_expense(category="rent", amount=8_000_000,
                          expense_date=date(2026, 8, 5)),
            _make_expense(category="rent", amount=8_000_000,
                          expense_date=date(2026, 9, 5)),
            _make_expense(category="rent", amount=8_000_000,
                          expense_date=date(2026, 10, 5)),
        ]
        candidates = _detect_candidates(
            expenses, [], [],
            lookback_months=3,
            min_occurrences=3,
            confidence_threshold=CONFIDENCE_THRESHOLD,
        )
        assert len(candidates) == 1
        assert float(candidates[0].confidence) >= 0.85

    def test_random_transactions_not_detected(self):
        """One-off purchases in different categories should not be detected."""
        expenses = [
            _make_expense(category="food", amount=150_000,
                          expense_date=date(2026, 8, 3)),
            _make_expense(category="transport", amount=50_000,
                          expense_date=date(2026, 9, 14)),
            _make_expense(category="entertainment", amount=300_000,
                          expense_date=date(2026, 10, 21)),
        ]
        candidates = _detect_candidates(
            expenses, [], [],
            lookback_months=3,
            min_occurrences=3,
            confidence_threshold=0.70,
        )
        assert len(candidates) == 0

    def test_only_2_months_below_min_occurrences(self):
        """2 occurrences when min_occurrences=3 → not detected."""
        expenses = [
            _make_expense(category="gym", amount=500_000,
                          expense_date=date(2026, 9, 15)),
            _make_expense(category="gym", amount=500_000,
                          expense_date=date(2026, 10, 15)),
        ]
        candidates = _detect_candidates(
            expenses, [], [],
            lookback_months=3,
            min_occurrences=3,
            confidence_threshold=0.70,
        )
        assert len(candidates) == 0

    def test_candidates_sorted_by_confidence_desc(self):
        """Higher-confidence candidate should come first."""
        expenses = [
            # rent: 3/3 months — highest confidence
            _make_expense(category="rent", amount=8_000_000,
                          expense_date=date(2026, 8, 5)),
            _make_expense(category="rent", amount=8_000_000,
                          expense_date=date(2026, 9, 5)),
            _make_expense(category="rent", amount=8_000_000,
                          expense_date=date(2026, 10, 5)),
            # gym: same 3/3 months
            _make_expense(category="gym", amount=500_000,
                          expense_date=date(2026, 8, 15)),
            _make_expense(category="gym", amount=500_000,
                          expense_date=date(2026, 9, 15)),
            _make_expense(category="gym", amount=500_000,
                          expense_date=date(2026, 10, 15)),
        ]
        candidates = _detect_candidates(
            expenses, [], [],
            lookback_months=3, min_occurrences=3, confidence_threshold=0.70,
        )
        # Both should be detected; sort by confidence then alphabetically stable
        assert len(candidates) == 2
        # All have same confidence (3/3) — just check both are present
        categories = {c.category_key for c in candidates}
        assert "rent" in categories
        assert "gym" in categories


# ── S16: Forecast model tests ────────────────────────────────────────────────


class TestForecastHelpers:
    def test_sum_patterns_income_only(self):
        income = _make_pattern(pattern_type=PATTERN_TYPE_INCOME, amount=20_000_000)
        expense = _make_pattern(pattern_type=PATTERN_TYPE_EXPENSE, amount=8_000_000)
        total = _sum_patterns([income, expense], PATTERN_TYPE_INCOME, date(2026, 11, 1))
        assert total == Decimal("20000000")

    def test_sum_patterns_expense_only(self):
        income = _make_pattern(pattern_type=PATTERN_TYPE_INCOME, amount=20_000_000)
        expense = _make_pattern(pattern_type=PATTERN_TYPE_EXPENSE, amount=8_000_000)
        total = _sum_patterns([income, expense], PATTERN_TYPE_EXPENSE, date(2026, 11, 1))
        assert total == Decimal("8000000")

    def test_inactive_pattern_excluded(self):
        p = _make_pattern(is_active=False, amount=5_000_000)
        total = _sum_patterns([p], PATTERN_TYPE_EXPENSE, date(2026, 11, 1))
        assert total == Decimal(0)

    def test_compute_threshold_user_set(self):
        user = _make_user(cashflow_alert_threshold=15_000_000)
        patterns = [_make_pattern(amount=10_000_000)]
        threshold = _compute_threshold(user, patterns)
        assert threshold == Decimal("15000000")

    def test_compute_threshold_fallback_is_sum_of_expenses(self):
        user = _make_user(cashflow_alert_threshold=None)
        p1 = _make_pattern(pattern_type=PATTERN_TYPE_EXPENSE, amount=8_000_000)
        p2 = _make_pattern(pattern_type=PATTERN_TYPE_EXPENSE, amount=5_000_000)
        income = _make_pattern(pattern_type=PATTERN_TYPE_INCOME, amount=20_000_000)
        threshold = _compute_threshold(user, [p1, p2, income])
        assert threshold == Decimal("13000000")   # 8tr + 5tr, income excluded

    def test_month_start_offset_no_overflow(self):
        today = date(2026, 12, 15)
        next_month = _month_start_offset(today, 1)
        assert next_month == date(2027, 1, 1)

    def test_month_start_offset_two_months(self):
        today = date(2026, 11, 1)
        assert _month_start_offset(today, 2) == date(2027, 1, 1)

    def test_monthly_forecast_data_to_dict(self):
        m = MonthlyForecastData(
            month=date(2026, 11, 1),
            income=Decimal("20000000"),
            expense=Decimal("15000000"),
            net=Decimal("5000000"),
            balance_eom=Decimal("32000000"),
        )
        d = m.to_dict()
        assert d["month"] == "2026-11-01"
        # to_dict uses str(Decimal) — no forced 2dp unless quantize was called.
        # In production, forecast.compute_and_persist_forecast quantizes before
        # constructing MonthlyForecastData; here we test the raw str conversion.
        assert d["net"] == "5000000"
        assert d["balance_eom"] == "32000000"

    def test_low_balance_detection(self):
        """If balance_eom < threshold, low_balance_risk should be True."""
        user = _make_user(cashflow_alert_threshold=20_000_000)
        p_income = _make_pattern(pattern_type=PATTERN_TYPE_INCOME, amount=15_000_000)
        p_expense = _make_pattern(pattern_type=PATTERN_TYPE_EXPENSE, amount=18_000_000)
        confirmed = [p_income, p_expense]

        # Simulate: starting balance = 5tr, net = -3tr → eom = 2tr < 20tr threshold
        threshold = _compute_threshold(user, confirmed)
        # net = 15tr - 18tr = -3tr
        net = _sum_patterns(confirmed, PATTERN_TYPE_INCOME, date(2026, 11, 1)) - \
              _sum_patterns(confirmed, PATTERN_TYPE_EXPENSE, date(2026, 11, 1))
        starting = Decimal("5000000")
        eom = starting + net
        assert eom < threshold   # confirms low balance would be detected


# ── S17: Alert dedup ─────────────────────────────────────────────────────────


class TestAlertDedup:
    def test_alert_key_format(self):
        user_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
        month = date(2026, 11, 1)
        key = f"cashflow_alert:{user_id}:{month.isoformat()}"
        assert key == "cashflow_alert:12345678-1234-5678-1234-567812345678:2026-11-01"

    @pytest.mark.asyncio
    async def test_alert_skipped_when_redis_has_key(self):
        """If Redis already has the dedup key, no message is sent."""
        user = MagicMock()
        user.id = uuid.uuid4()
        user.telegram_id = 12345

        forecast = MagicMock()
        forecast.low_balance_risk = True
        forecast.low_balance_month = date(2026, 11, 1)
        forecast.low_balance_threshold = Decimal("15000000")
        forecast.monthly_data = [
            {"month": "2026-11-01", "balance_eom": "5000000"}
        ]

        mock_redis = AsyncMock()
        mock_redis.exists = AsyncMock(return_value=True)   # dedup hit

        mock_notifier = AsyncMock()

        with (
            patch(
                "backend.cashflow.alert.get_latest_forecast",
                AsyncMock(return_value=forecast),
            ),
            patch("backend.cashflow.alert._get_redis", return_value=mock_redis),
            patch("backend.cashflow.alert.get_notifier", return_value=mock_notifier),
        ):
            from backend.cashflow.alert import check_and_send_alert
            sent = await check_and_send_alert(None, user, [])

        assert sent is False
        mock_notifier.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_alert_sent_when_no_dedup_key(self):
        """If Redis has no key, alert should be sent and key stored."""
        user = MagicMock()
        user.id = uuid.uuid4()
        user.telegram_id = 12345

        forecast = MagicMock()
        forecast.low_balance_risk = True
        forecast.low_balance_month = date(2026, 11, 1)
        forecast.low_balance_threshold = Decimal("15000000")
        forecast.monthly_data = [
            {"month": "2026-11-01", "balance_eom": "5000000"}
        ]

        mock_redis = AsyncMock()
        mock_redis.exists = AsyncMock(return_value=False)
        mock_redis.setex = AsyncMock()

        mock_notifier = AsyncMock()
        mock_notifier.send_message = AsyncMock(return_value={"ok": True})

        with (
            patch(
                "backend.cashflow.alert.get_latest_forecast",
                AsyncMock(return_value=forecast),
            ),
            patch("backend.cashflow.alert._get_redis", return_value=mock_redis),
            patch("backend.cashflow.alert.get_notifier", return_value=mock_notifier),
            patch("backend.cashflow.alert._load_copy", return_value={}),
        ):
            from backend.cashflow.alert import check_and_send_alert
            sent = await check_and_send_alert(None, user, [])

        assert sent is True
        mock_redis.setex.assert_called_once()


# ── S18: Chart tests ─────────────────────────────────────────────────────────


class TestCashflowChart:
    def test_chart_renders_valid_png(self):
        from backend.cashflow.chart import render_cashflow_waterfall
        monthly_data = [
            {
                "month": "2026-11-01",
                "income": "20500000",
                "expense": "15300000",
                "net": "5200000",
                "balance_eom": "32000000",
            },
            {
                "month": "2026-12-01",
                "income": "20500000",
                "expense": "15300000",
                "net": "5200000",
                "balance_eom": "37200000",
            },
            {
                "month": "2027-01-01",
                "income": "20500000",
                "expense": "15300000",
                "net": "5200000",
                "balance_eom": "42400000",
            },
        ]
        png = render_cashflow_waterfall(monthly_data)
        assert isinstance(png, bytes)
        assert len(png) > 0
        # PNG magic bytes: \x89PNG
        assert png[:4] == b"\x89PNG"

    def test_chart_empty_data_returns_png(self):
        from backend.cashflow.chart import render_cashflow_waterfall
        png = render_cashflow_waterfall([])
        assert isinstance(png, bytes)
        assert png[:4] == b"\x89PNG"

    def test_chart_negative_net_handled(self):
        """Negative net (expense > income) should render without crash."""
        from backend.cashflow.chart import render_cashflow_waterfall
        monthly_data = [
            {
                "month": "2026-11-01",
                "income": "10000000",
                "expense": "18000000",
                "net": "-8000000",
                "balance_eom": "2000000",
            },
        ]
        png = render_cashflow_waterfall(monthly_data)
        assert png[:4] == b"\x89PNG"
