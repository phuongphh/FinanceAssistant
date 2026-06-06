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


# ---------------------------------------------------------------------------
# Mode 1 — year-bearing date sitting anywhere in the message. The explicit
# year disambiguates from ratios; lookarounds keep the regex out of digit
# runs like phone numbers.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        # Leading year-bearing date — the original screenshot bug.
        ("14/05/2026 ăn gà kfc 120k", date(2026, 5, 14)),
        # Mid-message year-bearing.
        ("ăn tối 1tr 16/05/2026", date(2026, 5, 16)),
        # Trailing year-bearing.
        ("-50k cà phê 02/06/2026", date(2026, 6, 2)),
        # Dash separator.
        ("14-05-2026 ăn tối 100k", date(2026, 5, 14)),
        # Dot separator.
        ("14.05.2026 ăn tối 100k", date(2026, 5, 14)),
        # 2-digit year.
        ("14/05/26 ăn tối 100k", date(2026, 5, 14)),
        # Money-in shape with leading date.
        ("15/01/2026 +5tr thưởng tết", date(2026, 1, 15)),
    ],
)
def test_extract_year_bearing_anywhere(text: str, expected: date) -> None:
    result = extract_transaction_date(text, today=_TODAY)
    assert result is not None, f"expected a date in {text!r}"
    assert result.value == expected


def test_year_bearing_invalid_returns_none() -> None:
    # Year-bearing but invalid (31 Feb) → None, caller defaults to today.
    assert extract_transaction_date("31/02/2026 ăn tối", today=_TODAY) is None


def test_year_bearing_inside_digit_run_ignored() -> None:
    # A phone number must NOT be parsed as a date — lookarounds prevent
    # the regex from biting into the middle of a digit run.
    assert extract_transaction_date("gọi 0902/05/2026", today=_TODAY) is None


def test_year_bearing_span_covers_only_token() -> None:
    text = "ăn tối 1tr 16/05/2026"
    result = extract_transaction_date(text, today=_TODAY)
    assert result is not None
    start, end = result.span
    assert text[start:end] == "16/05/2026"


def test_keyword_beats_year_bearing_when_both_present() -> None:
    # Mode 0 wins over Mode 1 because the keyword is the most
    # authoritative shape.
    text = "ăn tối ngày 16/05 hôm 25/12/2025 quên"
    result = extract_transaction_date(text, today=_TODAY)
    assert result is not None
    assert result.value == date(2026, 5, 16)


# ---------------------------------------------------------------------------
# Mode 2 — leading bare ``dd/mm`` followed by more content, disambiguated
# by ``day > 12 OR month > 12``. Conservative on purpose: ratios like
# ``1/2 ổ bánh mì`` or ``12/3 phần`` stay untouched.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected_month,expected_day",
    [
        ("14/05 ăn gà 120k", 5, 14),  # day > 12
        ("25/06 cà phê 50k", 6, 25),  # day > 12
        ("31/01 tiền lương 5tr", 1, 31),  # day > 12
    ],
)
def test_extract_leading_bare_dd_mm_when_disambiguated(
    text: str, expected_month: int, expected_day: int
) -> None:
    result = extract_transaction_date(text, today=_TODAY)
    assert result is not None, f"expected a date in {text!r}"
    assert result.value.month == expected_month
    assert result.value.day == expected_day


@pytest.mark.parametrize(
    "text",
    [
        # Both <=12 → ambiguous (could be a ratio). Bail out rather than
        # risk parsing "1/2 ổ bánh mì 50k" as 1 Feb.
        "1/2 ổ bánh mì 50k",
        "12/3 phần pizza 50k",
        "5/6 ly nước 30k",
        # Leading dd/mm with NOTHING after — not a transaction shape.
        "14/05",
    ],
)
def test_leading_bare_dd_mm_rejected_when_ambiguous(text: str) -> None:
    assert extract_transaction_date(text, today=_TODAY) is None


def test_leading_bare_dd_mm_span_covers_only_token() -> None:
    text = "14/05 ăn gà 120k"
    result = extract_transaction_date(text, today=_TODAY)
    assert result is not None
    start, end = result.span
    assert text[start:end] == "14/05"


def test_leading_bare_dd_mm_defaults_to_today_year() -> None:
    text = "14/05 ăn gà 120k"
    result = extract_transaction_date(text, today=_TODAY)
    assert result is not None
    assert result.value.year == _TODAY.year


# ---------------------------------------------------------------------------
# Strip-span integration — the leading-date and trailing-date variants
# must leave clean merchant text behind.
# ---------------------------------------------------------------------------


def test_strip_span_removes_leading_year_bearing_date() -> None:
    text = "14/05/2026 ăn gà kfc 120k"
    result = extract_transaction_date(text, today=_TODAY)
    assert result is not None
    stripped = strip_span(text, result.span)
    assert "14/05" not in stripped
    assert stripped == "ăn gà kfc 120k"


def test_strip_span_removes_trailing_year_bearing_date() -> None:
    text = "-50k cà phê 02/06/2026"
    result = extract_transaction_date(text, today=_TODAY)
    assert result is not None
    stripped = strip_span(text, result.span)
    assert "02/06" not in stripped
    assert stripped == "-50k cà phê"


def test_strip_span_removes_leading_bare_dd_mm() -> None:
    text = "14/05 ăn gà 120k"
    result = extract_transaction_date(text, today=_TODAY)
    assert result is not None
    stripped = strip_span(text, result.span)
    assert stripped == "ăn gà 120k"
