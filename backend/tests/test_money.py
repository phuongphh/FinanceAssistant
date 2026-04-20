"""Tests for money formatters (Issue #27)."""
from backend.bot.formatters.money import format_money_full, format_money_short


class TestFormatMoneyShort:
    def test_below_1k(self):
        assert format_money_short(500) == "500đ"

    def test_exact_k(self):
        assert format_money_short(45_000) == "45k"

    def test_decimal_k(self):
        assert format_money_short(45_500) == "45.5k"

    def test_exact_tr(self):
        assert format_money_short(25_000_000) == "25tr"

    def test_decimal_tr(self):
        assert format_money_short(1_500_000) == "1.5tr"

    def test_billion(self):
        assert format_money_short(1_200_000_000) == "1.2 tỷ"

    def test_zero(self):
        assert format_money_short(0) == "0đ"

    def test_negative(self):
        assert format_money_short(-45_000) == "-45k"


class TestFormatMoneyFull:
    def test_small(self):
        assert format_money_full(45_000) == "45,000đ"

    def test_million(self):
        assert format_money_full(1_500_000) == "1,500,000đ"

    def test_zero(self):
        assert format_money_full(0) == "0đ"

    def test_float_rounds(self):
        assert format_money_full(12345.6) == "12,346đ"
