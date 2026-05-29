"""Unit tests for the centralized Vietnam-time helpers.

These lock in the contract that every user-facing timestamp renders in
``Asia/Ho_Chi_Minh`` (UTC+7) regardless of the server's clock — the bug
that recurred because call sites used naive ``datetime.now()`` or a bare
``.astimezone()`` (both system-local) instead of an explicit VN conversion.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from backend.utils.time_vn import VN_TZ, format_vn, now_vn, to_vn


def test_now_vn_offset_is_plus_seven():
    assert now_vn().utcoffset().total_seconds() == 7 * 3600


def test_to_vn_treats_naive_as_utc():
    # Naive UTC midnight is the historical ``datetime.utcnow`` shape.
    result = to_vn(datetime(2026, 5, 29, 0, 0, 0))
    assert result.strftime("%H:%M") == "07:00"
    assert result.tzinfo == VN_TZ


def test_to_vn_shifts_aware_utc():
    result = to_vn(datetime(2026, 5, 29, 0, 0, 0, tzinfo=timezone.utc))
    assert result.strftime("%H:%M") == "07:00"


def test_to_vn_preserves_instant_across_zones():
    # An aware value already in another zone must convert by instant, not
    # by wall clock.
    tokyo = datetime(2026, 5, 29, 9, 0, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    assert to_vn(tokyo).strftime("%H:%M") == "07:00"  # JST+9 -> ICT+7


def test_to_vn_none_passthrough():
    assert to_vn(None) is None


def test_format_vn_default_on_none():
    assert format_vn(None, "%H:%M", default="--:--") == "--:--"


def test_format_vn_renders_vn_clock():
    assert format_vn(datetime(2026, 5, 29, 0, 30), "%H:%M") == "07:30"
