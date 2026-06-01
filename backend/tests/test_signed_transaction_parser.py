"""Regression tests for the explicit-sign quick-syntax parser.

Convention:
  * Leading ``+`` → money-in (income)
  * Leading ``-`` (or no sign) → expense
  * Description after the amount is OPTIONAL — bare ``+200k`` / ``-50k``
    must still be recognised so the source-picker wizard fires.

Bare numbers like ``200`` (no sign, no unit, no description) stay
ambiguous and are deferred to the intent pipeline.
"""

from __future__ import annotations

import pytest

from backend.bot.handlers.message import (
    _parse_duoc_money_in,
    _parse_signed_transaction,
)
from backend.intent.handlers.action_quick_transaction import (
    _has_leading_plus_sign,
    _looks_like_income,
)


@pytest.mark.parametrize(
    "text,expected_type,expected_amount,expected_merchant",
    [
        ("+200k", "money_in", 200_000, ""),
        ("-200k", "expense", 200_000, ""),
        ("+200k lương", "money_in", 200_000, "lương"),
        ("-50k cà phê", "expense", 50_000, "cà phê"),
        ("+5tr thưởng tết", "money_in", 5_000_000, "thưởng tết"),
        ("+20tr5", "money_in", 20_500_000, ""),
        ("+510tr215", "money_in", 510_215_000, ""),
        ("200k cà phê", "expense", 200_000, "cà phê"),  # no sign → expense
        ("+ 200k", "money_in", 200_000, ""),  # space after sign
        (" -50k taxi ", "expense", 50_000, "taxi"),  # leading/trailing space
    ],
)
def test_parse_signed_transaction_accepts(
    text: str, expected_type: str, expected_amount: float, expected_merchant: str
) -> None:
    parsed = _parse_signed_transaction(text)
    assert parsed is not None, f"expected a parse for {text!r}"
    assert parsed["transaction_type"] == expected_type
    assert parsed["amount"] == expected_amount
    assert parsed["merchant"] == expected_merchant


@pytest.mark.parametrize(
    "text",
    [
        "200",  # bare number — too ambiguous
        "",
        "hôm nay đẹp trời",
        "báo cáo tháng này",
    ],
)
def test_parse_signed_transaction_rejects(text: str) -> None:
    assert _parse_signed_transaction(text) is None


def test_plus_sign_routes_through_income_guard() -> None:
    """The expense handler's guard must trip on a leading '+' so the
    handler never silently records '+200k' as an expense."""
    assert _has_leading_plus_sign("+200k") is True
    assert _has_leading_plus_sign(" + 200k tiền tip") is True
    assert _has_leading_plus_sign("-200k") is False
    assert _has_leading_plus_sign("200k cà phê") is False
    assert _looks_like_income("+200k") is True
    assert _looks_like_income("-200k") is False
    assert _looks_like_income("200k cà phê") is False


@pytest.mark.parametrize(
    "text,expected_amount,expected_merchant",
    [
        ("được bố cho 500k", 500_000, "bố cho"),
        ("được thưởng 200k", 200_000, "thưởng"),
        ("được lì xì 50k trên momo", 50_000, "lì xì trên momo"),
        ("được mẹ cho 1tr", 1_000_000, "mẹ cho"),
        ("được mừng tuổi 100k", 100_000, "mừng tuổi"),
        # Refund inflow: the "mua" reference to the original purchase must
        # not block the money-in parse.
        ("được hoàn 200k tiền mua vé", 200_000, "hoàn tiền mua vé"),
        # Found money: cash picked up records as money-in.
        ("tìm được 200k dưới gối", 200_000, "tìm được dưới gối"),
    ],
)
def test_parse_duoc_money_in_accepts(
    text: str, expected_amount: float, expected_merchant: str
) -> None:
    """'được <giver> cho/tặng/lì xì/thưởng <amount>' must parse as money-in
    so the Chi tiêu menu promise ('được bố cho 500k' → tiền vào) holds."""
    parsed = _parse_duoc_money_in(text)
    assert parsed is not None, f"expected a money-in parse for {text!r}"
    assert parsed["transaction_type"] == "money_in"
    assert parsed["amount"] == expected_amount
    assert parsed["merchant"] == expected_merchant
    assert parsed["note"] == text


@pytest.mark.parametrize(
    "text",
    [
        "mua được áo 200k",  # resultative được → expense, not income
        "tìm được quán ngon 150k",
        "tìm được thắt lưng 500k",  # found an OBJECT worth 500k, not cash
        "được thưởng bao nhiêu?",  # question
        "được thưởng 5tr rồi tiêu hết",  # spend verb wins
        "được nghỉ hôm nay",  # no amount, no giving verb
        "50k cà phê",  # plain expense
        "",
    ],
)
def test_parse_duoc_money_in_rejects(text: str) -> None:
    assert _parse_duoc_money_in(text) is None
