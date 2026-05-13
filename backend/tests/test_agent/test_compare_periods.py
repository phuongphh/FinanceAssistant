"""ComparePeriodsTool tests — period bounds + diff math.

Most of the value here is verifying the date math in
``_period_bounds`` (off-by-one is a classic bug for "this month
inclusive of today vs last calendar month")."""
from __future__ import annotations

from datetime import date

from backend.agent.tools.compare_periods import _period_bounds
from backend.agent.tools.schemas import ComparePeriod


class TestPeriodBounds:
    def test_this_month_runs_to_today(self):
        today = date(2026, 5, 15)
        start, end = _period_bounds(ComparePeriod.THIS_MONTH, today=today)
        assert start == date(2026, 5, 1)
        assert end == today

    def test_last_month_full_calendar_month(self):
        today = date(2026, 5, 15)
        start, end = _period_bounds(ComparePeriod.LAST_MONTH, today=today)
        assert start == date(2026, 4, 1)
        assert end == date(2026, 4, 30)

    def test_last_month_at_year_boundary(self):
        today = date(2026, 1, 10)
        start, end = _period_bounds(ComparePeriod.LAST_MONTH, today=today)
        assert start == date(2025, 12, 1)
        assert end == date(2025, 12, 31)

    def test_this_year_to_today(self):
        today = date(2026, 5, 15)
        start, end = _period_bounds(ComparePeriod.THIS_YEAR, today=today)
        assert start == date(2026, 1, 1)
        assert end == today

    def test_last_year_full_calendar_year(self):
        today = date(2026, 5, 15)
        start, end = _period_bounds(ComparePeriod.LAST_YEAR, today=today)
        assert start == date(2025, 1, 1)
        assert end == date(2025, 12, 31)
