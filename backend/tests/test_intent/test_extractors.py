"""Tests for the parameter extractors."""
from __future__ import annotations

from datetime import date

import pytest

from backend.intent.extractors import amount, category, goal_name, ticker, time_range


class TestTimeRange:
    @pytest.mark.parametrize(
        "text,expected_label",
        [
            ("hôm nay", "today"),
            ("hôm qua", "yesterday"),
            ("tuần này", "this_week"),
            ("tuần trước", "last_week"),
            ("tuần qua", "last_week"),
            ("tháng này", "this_month"),
            ("tháng trước", "last_month"),
            ("tháng qua", "last_month"),
            ("năm nay", "this_year"),
            ("năm ngoái", "last_year"),
            # Diacritic-stripped forms — same patterns must hit.
            ("thang nay", "this_month"),
            ("thang truoc", "last_month"),
        ],
    )
    def test_recognised_labels(self, text, expected_label):
        result = time_range.extract(text)
        assert result is not None
        assert result.label == expected_label

    def test_returns_none_for_no_match(self):
        assert time_range.extract("không có gì") is None
        assert time_range.extract("") is None

    def test_january_last_month_wraps_to_december(self):
        jan_today = date(2026, 1, 15)
        result = time_range.extract("tháng trước", today=jan_today)
        assert result is not None
        assert result.start == date(2025, 12, 1)
        assert result.end == date(2025, 12, 31)

    def test_this_month_range_starts_first_of_month(self):
        today = date(2026, 4, 17)
        result = time_range.extract("tháng này", today=today)
        assert result is not None
        assert result.start == date(2026, 4, 1)
        assert result.end == today


class TestCategory:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("ăn uống tháng này", "food"),
            ("an uong thang nay", "food"),
            ("chi cho cafe", "food"),
            ("phí grab", "transport"),
            ("tiền thuê nhà", "housing"),
            ("mua sắm quần áo", "shopping"),
            ("khám bệnh", "health"),
            ("học phí", "education"),
            ("xem phim", "entertainment"),
            ("netflix", "utility"),
            ("quà tặng sinh nhật", "gift"),
            ("đầu tư cổ phiếu", "investment"),
        ],
    )
    def test_keyword_match(self, text, expected):
        assert category.extract(text) == expected

    def test_returns_none_when_no_keyword(self):
        assert category.extract("không liên quan") is None
        assert category.extract("") is None


class TestTicker:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("VNM giá bao nhiêu", "VNM"),
            ("giá VCB hôm nay", "VCB"),
            ("VN-Index hôm nay", "VNINDEX"),
            ("VNINDEX", "VNINDEX"),
            ("vn-index", "VNINDEX"),
            ("BTC giá", "BTC"),
            ("bitcoin giá bao nhiêu", "BTC"),
            ("ethereum giá hôm nay", "ETH"),
            ("FPT đang lên không", "FPT"),
        ],
    )
    def test_recognised_tickers(self, text, expected):
        assert ticker.extract(text) == expected

    def test_unknown_ticker_returns_none(self):
        # "BAN" looks like a 3-letter ticker but isn't in the whitelist.
        assert ticker.extract("BAN HÀNG NHANH") is None

    def test_empty_returns_none(self):
        assert ticker.extract("") is None


class TestAmount:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("tiết kiệm 1tr", 1_000_000),
            ("500k", 500_000),
            ("2 triệu", 2_000_000),
            ("1.5 tỷ", 1_500_000_000),
            ("100,000 đ", 100_000),
            ("50000", 50_000),
        ],
    )
    def test_amount_extraction(self, text, expected):
        assert amount.extract(text) == expected

    def test_bare_small_number_rejected(self):
        # "5" or "10" alone is too ambiguous to read as VND.
        assert amount.extract("5") is None
        assert amount.extract("10") is None

    def test_negative_or_zero_rejected(self):
        assert amount.extract("0") is None
        assert amount.extract("") is None


class TestGoalName:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("muốn đạt được việc mua xe tôi cần phải làm gì?", "mua xe"),
            ("để mua nhà tôi cần làm sao", "nhà"),
            ("muốn có được căn hộ thì phải làm gì", "căn hộ"),
        ],
    )
    def test_extracts_goal_phrase(self, text, expected):
        result = goal_name.extract(text)
        assert result is not None
        # The heuristic may over- or under-strip leading words; we
        # require the meaningful noun to land in the result.
        assert expected in result.lower()

    def test_returns_none_for_unrelated_text(self):
        assert goal_name.extract("hôm nay trời đẹp quá") is None
        assert goal_name.extract("") is None
