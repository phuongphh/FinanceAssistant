"""Issue #897 — confirm message must render timestamps in Vietnam time.

The conversion lives in the formatter so no call site can forget. These
tests exercise the public contract by inspecting the rendered text.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from backend.bot.formatters.templates import (
    format_transaction_batch_confirmation,
    format_transaction_confirmation,
)


def _render_single(time):
    return format_transaction_confirmation(
        merchant="Phở",
        amount=45000,
        category_code="food_drink",
        time=time,
    )


def test_formatter_converts_utc_to_ict():
    utc = datetime(2026, 5, 28, 5, 15, tzinfo=timezone.utc)
    assert "12:15" in _render_single(utc)


def test_formatter_treats_naive_as_utc():
    naive = datetime(2026, 5, 28, 5, 15)
    assert "12:15" in _render_single(naive)


def test_formatter_passes_aware_local_through():
    aware = datetime(2026, 5, 28, 12, 15, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
    assert "12:15" in _render_single(aware)


def test_formatter_none_time_omits_clock():
    text = _render_single(None)
    assert "12:15" not in text
    assert ":15" not in text


def test_batch_formatter_converts_utc_to_ict():
    utc = datetime(2026, 5, 28, 5, 15, tzinfo=timezone.utc)
    text = format_transaction_batch_confirmation(
        items=[("Phở", 45000, "food_drink"), ("Trà", 20000, "food_drink")],
        time=utc,
    )
    assert "12:15" in text
