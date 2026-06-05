"""Tests for money formatters.

Rounding rule: short-form numbers are rounded only to the nearest 1,000đ
so a 2,350,000đ money-in transaction renders as "2tr350", not "2.4tr"
(see issue: money-in badge rounded down to nearest 100k).
"""
from decimal import Decimal

from backend.bot.formatters.money import format_money_full, format_money_short


class TestFormatMoneyShort:
    def test_zero(self):
        assert format_money_short(0) == "0đ"

    def test_below_1k(self):
        assert format_money_short(500) == "500đ"

    def test_sub_dong_rounds_to_zero(self):
        assert format_money_short(0.4) == "0đ"

    def test_exact_k(self):
        assert format_money_short(45_000) == "45k"

    def test_round_to_nearest_k(self):
        # 45,499 → 45k; 45,500 → 46k (banker's not used — half rounds away)
        assert format_money_short(45_499) == "45k"
        assert format_money_short(45_500) == "46k"

    def test_exact_tr_no_thousand_portion(self):
        assert format_money_short(25_000_000) == "25tr"

    def test_million_with_thousand_portion_user_example(self):
        # User's reported bug: 2,350,000đ must render as "2tr350", not "2.4tr".
        assert format_money_short(2_350_000) == "2tr350"

    def test_million_rounds_down_to_nearest_thousand(self):
        # 2,350,400 → still rounds to 2tr350
        assert format_money_short(2_350_400) == "2tr350"

    def test_million_rounds_up_to_nearest_thousand(self):
        # 2,350,500 → rounds up to 2tr351
        assert format_money_short(2_350_500) == "2tr351"

    def test_million_with_small_thousand_pads_to_three_digits(self):
        # Avoid ambiguity: "1tr050" reads as 1,050,000 — "1tr50" could be misread.
        assert format_money_short(1_050_000) == "1tr050"
        assert format_money_short(1_001_000) == "1tr001"

    def test_decimal_million_legacy_now_preserves_precision(self):
        # Old behaviour returned "1.5tr"; new rule shows the full thousand portion.
        assert format_money_short(1_500_000) == "1tr500"

    def test_billion_exact(self):
        assert format_money_short(2_000_000_000) == "2 tỷ"

    def test_billion_with_million_portion(self):
        assert format_money_short(1_200_000_000) == "1tỷ200"

    def test_billion_rounds_to_nearest_million(self):
        # Sub-tr precision in tỷ range is rounded to keep the badge short on mobile.
        assert format_money_short(1_234_567_890) == "1tỷ235"

    def test_negative_million(self):
        assert format_money_short(-2_350_000) == "-2tr350"

    def test_negative_k(self):
        assert format_money_short(-45_000) == "-45k"

    def test_decimal_input(self):
        assert format_money_short(Decimal("2350000")) == "2tr350"

    def test_float_input(self):
        assert format_money_short(2_350_000.0) == "2tr350"


class TestFormatMoneyFull:
    def test_small(self):
        assert format_money_full(45_000) == "45,000đ"

    def test_million(self):
        assert format_money_full(1_500_000) == "1,500,000đ"

    def test_zero(self):
        assert format_money_full(0) == "0đ"

    def test_float_rounds(self):
        assert format_money_full(12345.6) == "12,346đ"

    def test_user_amount_full_precision(self):
        assert format_money_full(2_350_000) == "2,350,000đ"
