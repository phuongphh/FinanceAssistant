"""Tests for the Tier-1 transaction-date extractor.

Anchored on Vietnamese date keywords (``ngày``, ``vào ngày``, ``hôm``) so
bare ratios like ``"ăn 12/3 phần pizza"`` MUST NOT be parsed as dates.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.bot.utils.transaction_date_extractor import (
    extract_transaction_date,
    strip_span,
)

_TODAY = date(2026, 6, 3)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("-1tr ăn tối ngày 16/05/2026", date(2026, 5, 16)),
        ("-1tr ăn tối ngày 16/05", date(2026, 5, 16)),
        ("100k cà phê vào ngày 01/05", date(2026, 5, 1)),
        ("ăn trưa 50k hôm 02/06", date(2026, 6, 2)),
        ("NGÀY 16/05/2026 ăn tối 1tr", date(2026, 5, 16)),  # case-insensitive
        ("được bố cho 500k ngày 15/05", date(2026, 5, 15)),
    ],
)
def test_extract_with_keyword_anchor(text: str, expected: date) -> None:
    result = extract_transaction_date(text, today=_TODAY)
    assert result is not None, f"expected a date in {text!r}"
    assert result.value == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "ăn 12/3 phần pizza",  # ratio — NOT a date phrase
        "mua 2/3 ổ bánh mì",  # portion
        "hôm nay đẹp trời",  # 'hôm' without a token
        "-1tr ăn tối",  # no date
        "100k cà phê",
        "ngày",  # keyword without token
    ],
)
def test_extract_returns_none_for_non_date(text: str) -> None:
    assert extract_transaction_date(text, today=_TODAY) is None


def test_extract_returns_none_for_invalid_token() -> None:
    # Keyword is present but the token is invalid → None (caller falls
    # back to date.today()).
    assert extract_transaction_date("ăn tối ngày 31/02", today=_TODAY) is None


def test_extract_span_covers_keyword_and_token() -> None:
    text = "-1tr ăn tối ngày 16/05/2026"
    result = extract_transaction_date(text, today=_TODAY)
    assert result is not None
    start, end = result.span
    assert text[start:end] == "ngày 16/05/2026"


def test_strip_span_removes_phrase_and_tidies_whitespace() -> None:
    text = "-1tr ăn tối ngày 16/05/2026"
    result = extract_transaction_date(text, today=_TODAY)
    assert result is not None
    stripped = strip_span(text, result.span)
    # Date phrase gone, no double spaces, no dangling punctuation.
    assert "ngày" not in stripped
    assert "16/05" not in stripped
    assert "  " not in stripped
    assert stripped == "-1tr ăn tối"


def test_strip_span_handles_mid_text_phrase() -> None:
    text = "ăn trưa ngày 02/06 ở quán cũ"
    result = extract_transaction_date(text, today=_TODAY)
    assert result is not None
    stripped = strip_span(text, result.span)
    assert stripped == "ăn trưa ở quán cũ"


def test_strip_span_empty_input() -> None:
    assert strip_span("", (0, 0)) == ""
