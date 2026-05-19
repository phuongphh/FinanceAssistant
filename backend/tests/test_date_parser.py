from datetime import date

from backend.bot.utils.date_parser import parse_vietnamese_date


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
