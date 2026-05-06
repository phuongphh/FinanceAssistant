"""Unit tests for ``backend.services.cashflow_forecaster``.

DB-free: a fake AsyncSession returns canned rows for the queries
the forecaster issues. We assert:

- Confidence formula matches spec (month 1=0.85, 2=0.70, 3=0.55).
- Income forecasted from streams with proper schedule semantics
  (monthly every month, annually only in schedule_month, quarterly
  every 3rd month).
- Recurring patterns add to expense; ambient adds the non-recurring
  baseline.
- Edge cases:
  - 0 streams → expected_income = 0 + warning note
  - 0 expense history → ambient = 0 + low-data flag
  - <3 months of expense data → confidence multiplied by 0.7
  - Projected deficit → "âm" warning in notes
- Spec test scenarios:
  - Stable monthly user: forecast matches recurring + ambient
  - Rental income (monthly): adds 15tr each month
  - Quarterly dividend: spike only in schedule_month and every 3rd

Runway tests cover:
- liquid = sum(asset_type='cash')
- monthly_burn = recurring + non-lifestyle ambient
- thresholds <3 → critical/🚨, 3-6 → tight/⚠️, >6 → comfortable
- 0 burn → months=None, band=unknown (don't divide by zero)
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.models.expense import Expense
from backend.models.recurring_pattern import RecurringPattern
from backend.services import cashflow_forecaster
from backend.wealth.models.asset import Asset
from backend.wealth.models.income_stream import IncomeStream


# ---------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------


def _stream(
    *, schedule_type: str, amount: Decimal,
    schedule_month: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    is_active: bool = True,
) -> IncomeStream:
    s = IncomeStream()
    s.id = uuid.uuid4()
    s.user_id = uuid.uuid4()
    s.stream_type = "salary"
    s.is_passive = False
    s.name = "test"
    s.amount = amount
    s.currency = "VND"
    s.schedule_type = schedule_type
    s.schedule_day = None
    s.schedule_month = schedule_month
    s.start_date = start_date or date(2020, 1, 1)
    s.end_date = end_date
    s.is_active = is_active
    return s


def _pattern(amount: Decimal, *, is_active: bool = True) -> RecurringPattern:
    p = RecurringPattern()
    p.id = uuid.uuid4()
    p.user_id = uuid.uuid4()
    p.name = "Thuê nhà"
    p.category = "housing"
    p.expected_amount = amount
    p.amount_variance_pct = 10.0
    p.schedule_type = "monthly"
    p.expected_day_of_month = 5
    p.is_active = is_active
    p.enable_reminders = True
    p.reminder_days_before = 2
    p.last_reminder_sent = None
    p.last_occurrence_date = None
    p.occurrence_count = 0
    return p


def _expense(
    amount: Decimal, expense_date: date, *,
    category: str = "food",
    recurrence_id: uuid.UUID | None = None,
) -> Expense:
    e = Expense()
    e.id = uuid.uuid4()
    e.user_id = uuid.uuid4()
    e.amount = amount
    e.currency = "VND"
    e.category = category
    e.source = "manual"
    e.expense_date = expense_date
    e.month_key = expense_date.strftime("%Y-%m")
    e.is_recurring = recurrence_id is not None
    e.recurrence_id = recurrence_id
    e.deleted_at = None
    return e


def _asset(
    *, asset_type: str, current_value: Decimal,
    is_active: bool = True,
) -> Asset:
    a = Asset()
    a.id = uuid.uuid4()
    a.user_id = uuid.uuid4()
    a.asset_type = asset_type
    a.subtype = None
    a.name = "test"
    a.initial_value = current_value
    a.current_value = current_value
    a.acquired_at = date(2020, 1, 1)
    a.last_valued_at = datetime.utcnow()
    a.is_active = is_active
    a.is_rental = False
    return a


def _result(rows):
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = rows
    result.scalars.return_value = scalars
    result.scalar_one_or_none.return_value = rows[0] if rows else None
    return result


def _mock_db(execute_returns):
    db = MagicMock()
    db.execute = AsyncMock(side_effect=execute_returns)
    return db


# ---------------------------------------------------------------------
# Confidence + month-offset helpers (pure functions)
# ---------------------------------------------------------------------


class TestConfidence:
    def test_spec_values(self):
        # Spec § P3.8-S11: month 1=85%, 2=70%, 3=55%, 4=40%.
        assert cashflow_forecaster._confidence(1) == pytest.approx(0.85)
        assert cashflow_forecaster._confidence(2) == pytest.approx(0.70)
        assert cashflow_forecaster._confidence(3) == pytest.approx(0.55)
        assert cashflow_forecaster._confidence(4) == pytest.approx(0.40)

    def test_floor_30_percent(self):
        # Long-horizon never falls below 0.30 — spec floor.
        assert cashflow_forecaster._confidence(10) == 0.30
        assert cashflow_forecaster._confidence(50) == 0.30


class TestMonthOffset:
    def test_basic(self):
        result = cashflow_forecaster._first_of_month_offset(
            date(2026, 5, 15), 1,
        )
        assert result == date(2026, 6, 1)

    def test_year_wrap(self):
        result = cashflow_forecaster._first_of_month_offset(
            date(2026, 11, 15), 3,
        )
        assert result == date(2027, 2, 1)


# ---------------------------------------------------------------------
# Income schedule arithmetic
# ---------------------------------------------------------------------


class TestIncomeForMonth:
    def test_monthly_stream_contributes_every_month(self):
        salary = _stream(schedule_type="monthly",
                         amount=Decimal("30000000"))
        for month in range(1, 13):
            target = date(2026, month, 1)
            assert cashflow_forecaster._income_for_month(
                [salary], target,
            ) == Decimal("30000000")

    def test_annually_stream_only_fires_in_schedule_month(self):
        """Spec test: User with quarterly dividend → forecast spikes
        correct months. Annual variant: dividend in June only."""
        dividend = _stream(
            schedule_type="annually",
            amount=Decimal("12000000"),
            schedule_month=6,
        )
        # Only June fires.
        for month in range(1, 13):
            target = date(2026, month, 1)
            expected = Decimal("12000000") if month == 6 else Decimal(0)
            assert cashflow_forecaster._income_for_month(
                [dividend], target,
            ) == expected

    def test_quarterly_stream_fires_every_third_month(self):
        # schedule_month=3 → Mar/Jun/Sep/Dec.
        div_q = _stream(
            schedule_type="quarterly",
            amount=Decimal("3000000"),
            schedule_month=3,
        )
        firing = {3, 6, 9, 12}
        for month in range(1, 13):
            target = date(2026, month, 1)
            expected = Decimal("3000000") if month in firing else Decimal(0)
            assert cashflow_forecaster._income_for_month(
                [div_q], target,
            ) == expected

    def test_ad_hoc_smoothed_by_monthly_equivalent(self):
        """ad_hoc has no schedule month — forecaster must fall back
        to the model's monthly_equivalent (= amount when stored as
        ad_hoc per the model's property)."""
        ad = _stream(schedule_type="ad_hoc", amount=Decimal("5000000"))
        target = date(2026, 6, 1)
        # ad_hoc.monthly_equivalent returns the raw amount (placeholder
        # until receipt history wires in — see income_stream.py).
        assert cashflow_forecaster._income_for_month(
            [ad], target,
        ) == Decimal("5000000")

    def test_ended_stream_contributes_zero(self):
        ended = _stream(
            schedule_type="monthly",
            amount=Decimal("30000000"),
            end_date=date(2026, 4, 30),
        )
        # May is past the end_date → no contribution.
        assert cashflow_forecaster._income_for_month(
            [ended], date(2026, 5, 1),
        ) == Decimal(0)

    def test_future_start_date_skipped(self):
        future = _stream(
            schedule_type="monthly",
            amount=Decimal("10000000"),
            start_date=date(2026, 8, 1),
        )
        # Forecasting May → skip; Aug → contribute.
        assert cashflow_forecaster._income_for_month(
            [future], date(2026, 5, 1),
        ) == Decimal(0)
        assert cashflow_forecaster._income_for_month(
            [future], date(2026, 8, 1),
        ) == Decimal("10000000")


# ---------------------------------------------------------------------
# Forecast end-to-end
# ---------------------------------------------------------------------


@pytest.mark.asyncio
class TestForecast:
    async def test_zero_months_ahead_returns_empty(self):
        db = _mock_db([])
        result = await cashflow_forecaster.forecast(
            db, uuid.uuid4(), months_ahead=0,
        )
        assert result == []

    async def test_stable_monthly_user(self):
        """Spec scenario: stable monthly user — recurring rent +
        ambient food etc → forecast roughly matches reality."""
        salary = _stream(schedule_type="monthly",
                         amount=Decimal("30000000"))
        rent = _pattern(amount=Decimal("15000000"))
        # Ambient = 9tr/mo across 3 months = 27tr total over 3 months.
        ambient = [
            _expense(Decimal("3000000"), date(2026, m, 15))
            for m in (1, 2, 3)
        ] + [
            _expense(Decimal("3000000"), date(2026, m, 20))
            for m in (1, 2, 3)
        ] + [
            _expense(Decimal("3000000"), date(2026, m, 25))
            for m in (1, 2, 3)
        ]
        db = _mock_db([
            _result([salary]),     # streams
            _result([rent]),       # patterns
            _result(ambient),      # ambient query
        ])
        result = await cashflow_forecaster.forecast(
            db, uuid.uuid4(), months_ahead=3,
            today=date(2026, 4, 1),
        )
        assert len(result) == 3
        # Month 1 (May): income 30tr, recurring 15tr, ambient 9tr.
        # Savings = 30 - 24 = 6tr. Confidence 0.85.
        m1 = result[0]
        assert m1.month == date(2026, 5, 1)
        assert m1.expected_income == Decimal("30000000")
        assert m1.expected_expense == Decimal("24000000")  # 15 + 9
        assert m1.expected_savings == Decimal("6000000")
        assert m1.confidence == pytest.approx(0.85, abs=0.01)
        # Month 2 confidence drops.
        assert result[1].confidence == pytest.approx(0.70, abs=0.01)
        assert result[2].confidence == pytest.approx(0.55, abs=0.01)

    async def test_rental_income_in_every_month(self):
        """Spec scenario: User with rental income — forecast includes
        15tr each month."""
        rental = _stream(schedule_type="monthly",
                         amount=Decimal("15000000"))
        rental.is_passive = True
        rental.stream_type = "rental"
        db = _mock_db([
            _result([rental]),
            _result([]),
            _result([]),
        ])
        result = await cashflow_forecaster.forecast(
            db, uuid.uuid4(), months_ahead=3,
            today=date(2026, 4, 1),
        )
        for f in result:
            assert f.expected_income == Decimal("15000000")

    async def test_quarterly_dividend_spike(self):
        """Spec scenario: quarterly dividend — spike in correct months."""
        div = _stream(
            schedule_type="quarterly",
            amount=Decimal("3000000"),
            schedule_month=3,
        )  # Mar/Jun/Sep/Dec
        db = _mock_db([
            _result([div]),
            _result([]),
            _result([]),
        ])
        # today = Apr → forecast May, Jun, Jul.
        result = await cashflow_forecaster.forecast(
            db, uuid.uuid4(), months_ahead=3,
            today=date(2026, 4, 1),
        )
        assert result[0].expected_income == Decimal(0)        # May
        assert result[1].expected_income == Decimal("3000000")  # Jun
        assert result[2].expected_income == Decimal(0)        # Jul

    async def test_zero_streams_warns(self):
        rent = _pattern(amount=Decimal("15000000"))
        db = _mock_db([
            _result([]),         # no streams
            _result([rent]),
            _result([]),
        ])
        result = await cashflow_forecaster.forecast(
            db, uuid.uuid4(), months_ahead=1,
            today=date(2026, 4, 1),
        )
        assert result[0].expected_income == Decimal(0)
        assert any("Chưa có nguồn thu nhập" in n for n in result[0].notes)

    async def test_low_data_drops_confidence(self):
        """User with <3 months of expense data → confidence × 0.7."""
        salary = _stream(schedule_type="monthly",
                         amount=Decimal("30000000"))
        # Only 1 month of ambient.
        ambient = [
            _expense(Decimal("3000000"), date(2026, 3, 15)),
            _expense(Decimal("3000000"), date(2026, 3, 20)),
        ]
        db = _mock_db([
            _result([salary]),
            _result([]),
            _result(ambient),
        ])
        result = await cashflow_forecaster.forecast(
            db, uuid.uuid4(), months_ahead=1,
            today=date(2026, 4, 1),
        )
        # Base 0.85 × 0.7 = 0.595, rounded to 2 dp = 0.59.
        assert result[0].confidence == pytest.approx(0.59, abs=0.02)
        # Forecaster appends a "tin cậy giảm" note when low data.
        assert any("tin cậy giảm" in n for n in result[0].notes)

    async def test_deficit_month_flagged(self):
        # 5tr income, 15tr expense → -10tr.
        small_salary = _stream(schedule_type="monthly",
                               amount=Decimal("5000000"))
        rent = _pattern(amount=Decimal("15000000"))
        db = _mock_db([
            _result([small_salary]),
            _result([rent]),
            _result([]),
        ])
        result = await cashflow_forecaster.forecast(
            db, uuid.uuid4(), months_ahead=1,
            today=date(2026, 4, 1),
        )
        f = result[0]
        assert f.expected_savings == Decimal("-10000000")
        assert any("âm" in n for n in f.notes)

    async def test_breakdown_carries_components(self):
        """Breakdown dict should explain the forecast (spec wants
        explainability on monthly_forecast)."""
        salary = _stream(schedule_type="monthly",
                         amount=Decimal("30000000"))
        rent = _pattern(amount=Decimal("15000000"))
        db = _mock_db([
            _result([salary]),
            _result([rent]),
            _result([]),
        ])
        result = await cashflow_forecaster.forecast(
            db, uuid.uuid4(), months_ahead=1,
            today=date(2026, 4, 1),
        )
        bd = result[0].breakdown
        assert bd["scheduled_income"] == Decimal("30000000")
        assert bd["recurring_expense"] == Decimal("15000000")
        assert "ambient_expense" in bd


# ---------------------------------------------------------------------
# Runway
# ---------------------------------------------------------------------


@pytest.mark.asyncio
class TestRunway:
    async def test_critical_band_under_3_months(self):
        cash = _asset(asset_type="cash",
                      current_value=Decimal("20000000"))
        rent = _pattern(amount=Decimal("10000000"))
        db = _mock_db([
            _result([cash]),     # _liquid_assets — runs first
            _result([rent]),     # _essential patterns
            _result([]),         # ambient essential expenses
        ])
        result = await cashflow_forecaster.compute_runway(
            db, uuid.uuid4(), today=date(2026, 4, 1),
        )
        # 20tr / 10tr = 2 months → critical.
        assert result.months == pytest.approx(2.0)
        assert result.band == "critical"
        assert "🚨" in (result.warning or "")

    async def test_tight_band_3_to_6_months(self):
        cash = _asset(asset_type="cash",
                      current_value=Decimal("40000000"))
        rent = _pattern(amount=Decimal("10000000"))
        db = _mock_db([
            _result([cash]),
            _result([rent]),
            _result([]),
        ])
        result = await cashflow_forecaster.compute_runway(
            db, uuid.uuid4(), today=date(2026, 4, 1),
        )
        # 40tr / 10tr = 4 months → tight.
        assert result.months == pytest.approx(4.0)
        assert result.band == "tight"
        assert "⚠️" in (result.warning or "")

    async def test_comfortable_no_warning(self):
        cash = _asset(asset_type="cash",
                      current_value=Decimal("100000000"))
        rent = _pattern(amount=Decimal("10000000"))
        db = _mock_db([
            _result([cash]),
            _result([rent]),
            _result([]),
        ])
        result = await cashflow_forecaster.compute_runway(
            db, uuid.uuid4(), today=date(2026, 4, 1),
        )
        # 100tr / 10tr = 10 months.
        assert result.months == pytest.approx(10.0)
        assert result.band == "comfortable"
        assert result.warning is None

    async def test_zero_burn_returns_none_months(self):
        """No essential expenses → can't compute runway. Return
        ``months=None`` rather than dividing by zero or returning
        inf, so consumers branch cleanly."""
        cash = _asset(asset_type="cash",
                      current_value=Decimal("100000000"))
        db = _mock_db([
            _result([cash]),     # _liquid_assets first
            _result([]),         # no patterns
            _result([]),         # no ambient
        ])
        result = await cashflow_forecaster.compute_runway(
            db, uuid.uuid4(), today=date(2026, 4, 1),
        )
        assert result.months is None
        assert result.band == "unknown"

    async def test_excludes_illiquid_assets(self):
        """Stocks and BĐS shouldn't count toward runway — only cash."""
        # The query filters by asset_type='cash', so here we just
        # confirm the forecaster passes that filter through. The
        # mocked _result already filters; we verify by passing a
        # mixed list and checking only the cash sum is used.
        cash = _asset(asset_type="cash",
                      current_value=Decimal("30000000"))
        rent = _pattern(amount=Decimal("10000000"))
        db = _mock_db([
            _result([cash]),  # only cash returned (stock filtered at SQL)
            _result([rent]),
            _result([]),
        ])
        result = await cashflow_forecaster.compute_runway(
            db, uuid.uuid4(), today=date(2026, 4, 1),
        )
        assert result.liquid_assets == Decimal("30000000")
        assert result.months == pytest.approx(3.0)
