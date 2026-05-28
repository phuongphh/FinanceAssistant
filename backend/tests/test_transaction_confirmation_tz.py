"""Issue #897 — confirm message must render timestamps in Vietnam time."""

from datetime import datetime, timezone

from backend.bot.handlers.callbacks import _to_vn_time


def test_to_vn_time_converts_utc_to_ict():
    utc = datetime(2026, 5, 28, 5, 15, tzinfo=timezone.utc)
    vn = _to_vn_time(utc)
    assert vn is not None
    assert vn.hour == 12
    assert vn.minute == 15


def test_to_vn_time_naive_treated_as_utc():
    naive = datetime(2026, 5, 28, 5, 15)
    vn = _to_vn_time(naive)
    assert vn is not None
    assert vn.hour == 12
    assert vn.minute == 15


def test_to_vn_time_passes_aware_local():
    from zoneinfo import ZoneInfo

    aware = datetime(2026, 5, 28, 12, 15, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
    vn = _to_vn_time(aware)
    assert vn is not None
    assert vn.hour == 12
    assert vn.minute == 15


def test_to_vn_time_none_returns_none():
    assert _to_vn_time(None) is None
