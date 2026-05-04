"""Tests for the USD↔VND helper used by the foreign-stock asset flow."""
from decimal import Decimal

import pytest

from backend.wealth.fx import USD_VND_RATE, parse_usd_amount, usd_to_vnd


def test_usd_to_vnd_multiplies_by_rate():
    assert usd_to_vnd(Decimal("150")) == Decimal("150") * USD_VND_RATE


def test_usd_to_vnd_handles_int_and_float_inputs():
    assert usd_to_vnd(150) == Decimal("150") * USD_VND_RATE
    assert usd_to_vnd(150.5) == Decimal("150.5") * USD_VND_RATE


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("150", Decimal("150")),
        ("150.5", Decimal("150.5")),
        ("$150", Decimal("150")),
        ("150 USD", Decimal("150")),
        ("150usd", Decimal("150")),
        ("1,500", Decimal("1500")),
        ("$1,500.25", Decimal("1500.25")),
        ("  150  ", Decimal("150")),
    ],
)
def test_parse_usd_amount_accepts_common_user_inputs(raw, expected):
    assert parse_usd_amount(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["", "  ", "abc", "$$", "USD", "1.2.3", "-150", "0"],
)
def test_parse_usd_amount_rejects_garbage_and_non_positive(raw):
    assert parse_usd_amount(raw) is None
