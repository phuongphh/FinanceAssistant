"""Tests for the Vietnamese-friendly money parser used by asset wizards."""
from __future__ import annotations

from decimal import Decimal

import pytest

from backend.wealth.amount_parser import (
    has_negative_sign,
    parse_amount,
    parse_label_and_amount,
)


class TestParseAmount:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("100 triệu", Decimal("100000000")),
            ("100tr", Decimal("100000000")),
            ("100 tr", Decimal("100000000")),
            ("100trieu", Decimal("100000000")),
            ("1.5 tỷ", Decimal("1500000000")),
            ("1,5 tỷ", Decimal("1500000000")),
            ("1.5ty", Decimal("1500000000")),
            ("500k", Decimal("500000")),
            ("500K", Decimal("500000")),
            ("500 nghìn", Decimal("500000")),
            ("500 ngàn", Decimal("500000")),
            ("45000", Decimal("45000")),
            ("45,000", Decimal("45000")),
            ("1,000,000", Decimal("1000000")),
            ("1.000.000", Decimal("1000000")),
        ],
    )
    def test_recognised_formats(self, raw, expected):
        assert parse_amount(raw) == expected

    @pytest.mark.parametrize(
        "raw,expected",
        [
            # "rưỡi" after a unit means "and a half of that unit".
            ("2 tỷ rưỡi", Decimal("2500000000")),
            ("2 ty ruoi", Decimal("2500000000")),
            ("1 tỷ rưỡi", Decimal("1500000000")),
            ("3 triệu rưỡi", Decimal("3500000")),
            ("3 trieu ruoi", Decimal("3500000")),
            ("3tr rưỡi", Decimal("3500000")),
            ("3trrưỡi", Decimal("3500000")),
            ("500 nghìn rưỡi", Decimal("500500")),
            ("500 ngan ruoi", Decimal("500500")),
            ("2 TỶ RƯỠI", Decimal("2500000000")),
            # Diacritic-less + spaced variant.
            ("10 ty ruoi", Decimal("10500000000")),
        ],
    )
    def test_ruoi_adds_half_unit(self, raw, expected):
        assert parse_amount(raw) == expected

    @pytest.mark.parametrize(
        "raw,expected",
        [
            # "rưỡi" without a real unit (or with đ) is nonsensical for
            # VND — we ignore it rather than adding 0.5đ.
            ("100 rưỡi", Decimal("100")),
            ("100đ rưỡi", Decimal("100")),
            ("100 d ruoi", Decimal("100")),
        ],
    )
    def test_ruoi_ignored_without_real_unit(self, raw, expected):
        assert parse_amount(raw) == expected

    def test_empty_returns_none(self):
        assert parse_amount("") is None
        assert parse_amount(None) is None  # type: ignore[arg-type]

    def test_garbage_returns_none(self):
        assert parse_amount("hôm qua trời mưa") is None


class TestParseLabelAndAmount:
    @pytest.mark.parametrize(
        "raw,expected_label,expected_amount",
        [
            ("VCB 100 triệu", "VCB", Decimal("100000000")),
            ("Techcom 50tr", "Techcom", Decimal("50000000")),
            ("MoMo 2tr", "MoMo", Decimal("2000000")),
            ("Tiết kiệm 500 nghìn", "Tiết kiệm", Decimal("500000")),
            ("5 triệu", "", Decimal("5000000")),
            ("100 triệu", "", Decimal("100000000")),
        ],
    )
    def test_examples_from_spec(self, raw, expected_label, expected_amount):
        result = parse_label_and_amount(raw)
        assert result is not None
        label, amount = result
        assert label == expected_label
        assert amount == expected_amount

    def test_zero_or_negative_rejected(self):
        # Parser returns positive amounts only; "0 triệu" → None
        assert parse_label_and_amount("0 triệu") is None

    @pytest.mark.parametrize(
        "raw,expected_label,expected_amount",
        [
            # Digits inside the label must NOT be read as the amount.
            # The bug was "VCB-001 100 triệu" parsing to 1đ because the
            # search greedily took "001" — the first digit run.
            ("VCB-001 100 triệu", "VCB-001", Decimal("100000000")),
            ("VCB-001 100tr", "VCB-001", Decimal("100000000")),
            ("TK-1234 50tr", "TK-1234", Decimal("50000000")),
            ("VCB-001 45000", "VCB-001", Decimal("45000")),
            ("ACB123 2 tỷ", "ACB123", Decimal("2000000000")),
        ],
    )
    def test_digits_in_label_are_not_amounts(
        self, raw, expected_label, expected_amount
    ):
        result = parse_label_and_amount(raw)
        assert result is not None, f"parser returned None for {raw!r}"
        label, amount = result
        assert label == expected_label
        assert amount == expected_amount

    def test_label_only_no_amount_returns_none(self):
        # "VCB-001" alone has digits but no free-standing amount — reject.
        assert parse_label_and_amount("VCB-001") is None

    @pytest.mark.parametrize(
        "raw,expected_label,expected_amount",
        [
            # Real-estate wizard regression: "Nhà 2 tỷ rưỡi" = 2.5 tỷ.
            ("Nhà 2 tỷ rưỡi", "Nhà", Decimal("2500000000")),
            ("Nhà phố 2 ty ruoi", "Nhà phố", Decimal("2500000000")),
            ("Đất Long An 1 tỷ rưỡi", "Đất Long An", Decimal("1500000000")),
            ("VCB 100 triệu rưỡi", "VCB", Decimal("100500000")),
            ("2 tỷ rưỡi", "", Decimal("2500000000")),
        ],
    )
    def test_ruoi_in_labeled_amount(
        self, raw, expected_label, expected_amount
    ):
        result = parse_label_and_amount(raw)
        assert result is not None, f"parser returned None for {raw!r}"
        label, amount = result
        assert label == expected_label
        assert amount == expected_amount


class TestHasNegativeSign:
    @pytest.mark.parametrize(
        "raw",
        [
            "-100 triệu",
            "VCB -100 triệu",
            "VCB -100tr",
            "  -45000",
            "Techcom -50tr",
        ],
    )
    def test_detects_negative(self, raw):
        assert has_negative_sign(raw) is True

    @pytest.mark.parametrize(
        "raw",
        [
            "VCB 100 triệu",
            "100tr",
            "VCB-001 100tr",  # label dash, not a sign
            "TK-1234 50tr",
            "",
            "ngày 1-2 chi 100k",  # range dash, not a sign
        ],
    )
    def test_does_not_flag_non_negative(self, raw):
        assert has_negative_sign(raw) is False
