from datetime import date

from backend.bot.utils.date_parser import (
    parse_vietnamese_date,
    parse_vietnamese_date_token,
)


def test_parse_vietnamese_date_accepts_slash_format() -> None:
    assert parse_vietnamese_date("31/12/2028") == date(2028, 12, 31)


def test_parse_vietnamese_date_accepts_dash_format() -> None:
    assert parse_vietnamese_date("31-12-2028") == date(2028, 12, 31)


def test_parse_vietnamese_date_accepts_iso_fallback() -> None:
    assert parse_vietnamese_date("2028-12-31") == date(2028, 12, 31)


def test_parse_vietnamese_date_strips_whitespace() -> None:
    assert parse_vietnamese_date("  01/02/2029  ") == date(2029, 2, 1)


def test_parse_vietnamese_date_returns_none_on_invalid() -> None:
    assert parse_vietnamese_date("31/31/2028") is None
    assert parse_vietnamese_date("not-a-date") is None
    assert parse_vietnamese_date("") is None


# ---------------------------------------------------------------------------
# parse_vietnamese_date_token — used by the NLU date extractor. Must accept
# year-less forms and 2-digit years; must reject malformed/out-of-range dates.
# ---------------------------------------------------------------------------


def test_token_parses_full_year() -> None:
    assert parse_vietnamese_date_token(
        "16/05/2026", today=date(2026, 6, 3)
    ) == date(2026, 5, 16)


def test_token_parses_year_less_form_defaults_to_today_year() -> None:
    assert parse_vietnamese_date_token(
        "16/05", today=date(2026, 6, 3)
    ) == date(2026, 5, 16)


def test_token_parses_two_digit_year_as_2000_offset() -> None:
    assert parse_vietnamese_date_token(
        "16/05/26", today=date(2026, 6, 3)
    ) == date(2026, 5, 16)


def test_token_accepts_dash_and_dot_separators() -> None:
    assert parse_vietnamese_date_token(
        "16-05-2026", today=date(2026, 6, 3)
    ) == date(2026, 5, 16)
    assert parse_vietnamese_date_token(
        "16.05.2026", today=date(2026, 6, 3)
    ) == date(2026, 5, 16)


def test_token_accepts_single_digit_day_and_month() -> None:
    assert parse_vietnamese_date_token(
        "5/3", today=date(2026, 6, 3)
    ) == date(2026, 3, 5)


def test_token_rejects_invalid_day_or_month() -> None:
    assert parse_vietnamese_date_token("31/02", today=date(2026, 6, 3)) is None
    assert parse_vietnamese_date_token("00/05", today=date(2026, 6, 3)) is None
    assert parse_vietnamese_date_token("16/13", today=date(2026, 6, 3)) is None


def test_token_rejects_empty_and_malformed() -> None:
    assert parse_vietnamese_date_token("", today=date(2026, 6, 3)) is None
    assert parse_vietnamese_date_token("hôm nay", today=date(2026, 6, 3)) is None
    assert parse_vietnamese_date_token("16", today=date(2026, 6, 3)) is None
