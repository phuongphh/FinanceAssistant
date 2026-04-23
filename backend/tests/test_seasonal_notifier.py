"""Unit tests for the seasonal notifier (Phase 2, Issue #43).

Focus on the deterministic pieces:
- Lunar + solar date resolution (Tết / Trung thu computed correctly).
- Year-rollover behaviour (Tết already past → resolve next year).
- Offset arithmetic.
- YAML has at least 8 events covering a full year.
- Dedup key format stable (event_name:year).
"""
from __future__ import annotations

from datetime import date

from backend.jobs import seasonal_notifier


class TestLunarSolarResolution:
    def test_fixed_solar_date(self):
        d = seasonal_notifier._resolve_trigger_date(
            {"solar": {"month": 11, "day": 25}}, date(2026, 4, 23),
        )
        assert d == date(2026, 11, 25)

    def test_solar_with_offset(self):
        d = seasonal_notifier._resolve_trigger_date(
            {"solar": {"month": 11, "day": 29, "offset_days": -4}},
            date(2026, 4, 23),
        )
        assert d == date(2026, 11, 25)

    def test_invalid_solar_date_returns_none(self):
        # Feb 29 in a non-leap year.
        d = seasonal_notifier._resolve_trigger_date(
            {"solar": {"month": 2, "day": 29}}, date(2025, 4, 23),
        )
        assert d is None

    def test_lunar_tet_in_current_year_if_not_past(self):
        # On 2026-01-15, Tết is still ahead (2026-02-17).
        d = seasonal_notifier._resolve_trigger_date(
            {"lunar": {"month": 1, "day": 1}}, date(2026, 1, 15),
        )
        assert d == date(2026, 2, 17)

    def test_lunar_tet_rolls_to_next_year_if_far_past(self):
        # On 2026-04-23 Tết 2026 (Feb 17) is 65 days past → resolver
        # should look ahead to Tết 2027 (2027-02-06) so the notifier
        # doesn't silently skip the event for the next year.
        d = seasonal_notifier._resolve_trigger_date(
            {"lunar": {"month": 1, "day": 1}}, date(2026, 4, 23),
        )
        assert d == date(2027, 2, 6)

    def test_lunar_mid_autumn_2026(self):
        # Mid-autumn 2026 = Lunar 2026-08-15 = solar 2026-09-25.
        d = seasonal_notifier._resolve_trigger_date(
            {"lunar": {"month": 8, "day": 15}}, date(2026, 4, 23),
        )
        assert d == date(2026, 9, 25)


class TestCalendarContent:
    def test_at_least_eight_events(self):
        seasonal_notifier.reload_calendar_for_tests()
        cal = seasonal_notifier._load_calendar()
        events = cal.get("events") or []
        assert len(events) >= 8
        names = {e["name"] for e in events}
        for required in (
            "tet_preparation", "tet_day", "post_tet_review", "mid_autumn",
            "back_to_school", "black_friday", "double_11", "year_end_review",
        ):
            assert required in names

    def test_every_event_has_name_message_and_when(self):
        seasonal_notifier.reload_calendar_for_tests()
        for ev in seasonal_notifier._load_calendar()["events"]:
            assert ev.get("name"), ev
            assert ev.get("message"), ev
            assert ev.get("when"), ev


class TestEventsFiringToday:
    def test_nothing_on_random_date(self):
        seasonal_notifier.reload_calendar_for_tests()
        # A date with no seasonal event configured.
        hits = seasonal_notifier._events_firing_today(date(2026, 4, 23))
        assert hits == []

    def test_black_friday_fires_on_nov_25(self):
        seasonal_notifier.reload_calendar_for_tests()
        hits = seasonal_notifier._events_firing_today(date(2026, 11, 25))
        names = [h["name"] for h in hits]
        assert "black_friday" in names

    def test_year_end_fires_on_dec_28(self):
        seasonal_notifier.reload_calendar_for_tests()
        hits = seasonal_notifier._events_firing_today(date(2026, 12, 28))
        assert any(h["name"] == "year_end_review" for h in hits)


class TestDedupKey:
    def test_key_format_stable(self):
        assert seasonal_notifier._dedup_key("mid_autumn", 2026) == "mid_autumn:2026"
