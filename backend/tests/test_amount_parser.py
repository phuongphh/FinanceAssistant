"""Tests for the Vietnamese-friendly money parser used by asset wizards."""
from __future__ import annotations

from decimal import Decimal

import pytest

from backend.wealth.amount_parser import parse_amount, parse_label_and_amount


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
