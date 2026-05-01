"""Vietnamese time-range extractor.

Recognises phrases users actually type — "hôm nay", "tuần này",
"tháng trước", with diacritic-insensitive matching so "thang nay"
works too. Returns ``TimeRange`` (start, end inclusive, label) or None.

The ``label`` doubles as a stable token for analytics + the
``expected_parameters.time_range`` key in test fixtures (e.g.
``this_month``, ``last_week``). UI strings re-derive labels from the
locale; don't display ``label`` directly to users.

Edge case: "tháng trước" in January wraps to December of the prior year.
"""
from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta

from backend.intent.extractors._normalize import strip_diacritics


@dataclass(frozen=True)
class TimeRange:
    start: date
    end: date
    label: str  # Stable analytics token: "today" | "this_month" | ...


# Order matters: the FIRST matching entry wins. Longer / more specific
# phrases come before shorter ones so "tháng trước" beats "tháng".
_PATTERNS: list[tuple[tuple[str, ...], str]] = [
    (("hom nay",), "today"),
    (("hom qua",), "yesterday"),
    (("tuan nay",), "this_week"),
    (("tuan truoc", "tuan qua"), "last_week"),
    (("thang nay",), "this_month"),
    (("thang truoc", "thang qua"), "last_month"),
    (("nam nay",), "this_year"),
    (("nam ngoai", "nam truoc"), "last_year"),
]


def _last_day_of_prev_month(today: date) -> date:
    first_of_this = today.replace(day=1)
    return first_of_this - timedelta(days=1)


def _build_range(label: str, today: date) -> TimeRange:
    if label == "today":
        return TimeRange(today, today, label)
    if label == "yesterday":
        d = today - timedelta(days=1)
        return TimeRange(d, d, label)
    if label == "this_week":
        start = today - timedelta(days=today.weekday())
        return TimeRange(start, today, label)
    if label == "last_week":
        # Monday of last week to Sunday of last week.
        start = today - timedelta(days=today.weekday() + 7)
        end = start + timedelta(days=6)
        return TimeRange(start, end, label)
    if label == "this_month":
        return TimeRange(today.replace(day=1), today, label)
    if label == "last_month":
        end = _last_day_of_prev_month(today)
        start = end.replace(day=1)
        return TimeRange(start, end, label)
    if label == "this_year":
        return TimeRange(date(today.year, 1, 1), today, label)
    if label == "last_year":
        last_year = today.year - 1
        return TimeRange(date(last_year, 1, 1), date(last_year, 12, 31), label)
    raise ValueError(f"Unknown label: {label!r}")


def extract(text: str, *, today: date | None = None) -> TimeRange | None:
    """Find a recognised time-range phrase. ``today`` is injectable for
    tests; defaults to ``date.today()``."""
    if not text:
        return None
    today = today or date.today()
    needle = strip_diacritics(text.lower())

    for keywords, label in _PATTERNS:
        if any(kw in needle for kw in keywords):
            return _build_range(label, today)
    return None


__all__ = ["TimeRange", "extract"]
