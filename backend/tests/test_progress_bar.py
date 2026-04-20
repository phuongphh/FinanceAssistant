"""Tests for progress bar formatter (Issue #27)."""
from backend.bot.formatters.progress_bar import make_category_bar, make_progress_bar


class TestMakeProgressBar:
    def test_half(self):
        assert make_progress_bar(50, 100, width=10) == "█████░░░░░ 50%"

    def test_full(self):
        assert make_progress_bar(100, 100, width=10) == "██████████ 100%"

    def test_empty(self):
        assert make_progress_bar(0, 100, width=10) == "░░░░░░░░░░ 0%"

    def test_over_100_percent(self):
        result = make_progress_bar(150, 100, width=10)
        assert "150%" in result
        # Bar phải full khi vượt — không tràn ra ngoài width
        assert result.count("█") == 10
        assert result.count("░") == 0

    def test_total_zero_handled(self):
        result = make_progress_bar(0, 0)
        assert "0%" in result
        assert "█" not in result

    def test_negative_total_handled(self):
        result = make_progress_bar(10, -5)
        assert "0%" in result

    def test_custom_width(self):
        result = make_progress_bar(50, 100, width=20)
        assert result.count("█") == 10
        assert result.count("░") == 10

    def test_rounds_percentage(self):
        # 215/400 = 53.75% → hiển thị 54%
        assert "54%" in make_progress_bar(215, 400, width=10)


class TestMakeCategoryBar:
    def test_no_percent_label(self):
        result = make_category_bar(50, 100, width=10)
        assert "%" not in result
        assert len(result) == 10

    def test_half(self):
        assert make_category_bar(50, 100, width=10) == "█████░░░░░"

    def test_max_amount_zero(self):
        assert make_category_bar(0, 0, width=10) == "░" * 10

    def test_over_max(self):
        # Bar phải full khi vượt max
        result = make_category_bar(500, 100, width=10)
        assert result == "█" * 10
