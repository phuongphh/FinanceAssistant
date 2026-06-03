"""Tests for message templates (Issue #27)."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from backend.bot.formatters.templates import (
    format_budget_alert,
    format_daily_summary,
    format_transaction_batch_confirmation,
    format_transaction_confirmation,
    format_welcome_message,
)

_VN = ZoneInfo("Asia/Ho_Chi_Minh")


class TestTransactionConfirmation:
    def test_basic_contains_emoji_and_amount(self):
        result = format_transaction_confirmation(
            merchant="Phở Bát Đàn",
            amount=45_000,
            category_code="food",
        )
        assert "✅ Đã ghi xong!" in result
        assert "Phở Bát Đàn" in result
        assert "45,000đ" in result
        assert "🍜" in result

    def test_with_location_and_time(self):
        result = format_transaction_confirmation(
            merchant="Highlands",
            amount=85_000,
            category_code="food",
            location="Hà Nội",
            time=datetime(2026, 4, 15, 12, 15, tzinfo=_VN),
        )
        assert "📍 Hà Nội" in result
        assert "12:15" in result

    def test_with_budget_progress_bar(self):
        result = format_transaction_confirmation(
            merchant="Highlands",
            amount=85_000,
            category_code="food",
            daily_spent=215_000,
            daily_budget=400_000,
        )
        assert "54%" in result  # 215/400 ≈ 54%
        assert "Còn 185k" in result
        assert "█" in result

    def test_over_budget_slight(self):
        result = format_transaction_confirmation(
            merchant="Lotte",
            amount=100_000,
            category_code="shopping",
            daily_spent=450_000,
            daily_budget=400_000,
        )
        assert "Đã vượt" in result
        assert "🫣" in result

    def test_over_budget_significant(self):
        result = format_transaction_confirmation(
            merchant="Lotte",
            amount=500_000,
            category_code="shopping",
            daily_spent=600_000,
            daily_budget=400_000,
        )
        assert "Vượt ngân sách" in result
        assert "😅" in result

    def test_source_label_and_edit_hint(self):
        result = format_transaction_confirmation(
            merchant="Sashimi cá hồi",
            amount=4_000_000,
            category_code="food",
            source_label="Thẻ tín dụng [Vietcombank]",
            show_edit_hint=True,
        )
        assert "Chi từ: Thẻ tín dụng [Vietcombank]" in result
        assert "chi tiêu đã được ghi lại" in result
        assert "Nếu thông tin chưa chính xác" in result
        assert "click vào các nhãn ở dưới để sửa lại" in result
        assert "<i>" in result and "</i>" in result
        assert "💡" in result

    def test_unknown_category_falls_back_to_other(self):
        result = format_transaction_confirmation(
            merchant="?",
            amount=10_000,
            category_code="not_a_real_category",
        )
        assert "📌" in result  # 'other' emoji

    def test_back_dated_expense_renders_date_line(self):
        result = format_transaction_confirmation(
            merchant="ăn tối",
            amount=1_000_000,
            category_code="food",
            expense_date=date(2026, 5, 16),
        )
        assert "📅 Ngày giao dịch: 16/05/2026" in result

    def test_today_expense_omits_date_line(self):
        result = format_transaction_confirmation(
            merchant="cà phê",
            amount=50_000,
            category_code="food",
            expense_date=date.today(),
        )
        assert "Ngày giao dịch" not in result

    def test_none_expense_date_omits_date_line(self):
        result = format_transaction_confirmation(
            merchant="cà phê",
            amount=50_000,
            category_code="food",
            expense_date=None,
        )
        assert "Ngày giao dịch" not in result


class TestTransactionBatchConfirmation:
    def test_contains_each_item_and_total(self):
        result = format_transaction_batch_confirmation(
            items=[("tiền xăng", 50_000, "transport"), ("ăn trưa", 50_000, "food")],
            time=datetime(2026, 5, 7, 19, 18, tzinfo=_VN),
        )
        assert "✅ Đã ghi xong 2 khoản!" in result
        assert "🚗 tiền xăng" in result
        assert "🍜 ăn trưa" in result
        assert "Tổng: 100,000đ" in result
        assert "19:18" in result

    def test_batch_source_label_and_edit_hint(self):
        result = format_transaction_batch_confirmation(
            items=[("tiền xăng", 50_000, "transport"), ("ăn trưa", 50_000, "food")],
            source_label="Tiền mặt",
            show_edit_hint=True,
        )
        assert "Chi từ: Tiền mặt" in result
        assert "chi tiêu đã được ghi lại" in result
        assert "Nếu thông tin chưa chính xác" in result
        assert "click vào các nhãn ở dưới để sửa lại" in result
        assert "<i>" in result and "</i>" in result
        assert "💡" in result

    def test_batch_back_dated_renders_date_line(self):
        yesterday = date.today() - timedelta(days=1)
        result = format_transaction_batch_confirmation(
            items=[("tiền xăng", 50_000, "transport"), ("ăn trưa", 50_000, "food")],
            expense_date=yesterday,
        )
        assert "Ngày giao dịch" in result
        assert yesterday.strftime("%d/%m/%Y") in result

    def test_batch_today_omits_date_line(self):
        result = format_transaction_batch_confirmation(
            items=[("tiền xăng", 50_000, "transport"), ("ăn trưa", 50_000, "food")],
            expense_date=date.today(),
        )
        assert "Ngày giao dịch" not in result

    def test_batch_none_expense_date_omits_date_line(self):
        result = format_transaction_batch_confirmation(
            items=[("tiền xăng", 50_000, "transport"), ("ăn trưa", 50_000, "food")],
            expense_date=None,
        )
        assert "Ngày giao dịch" not in result


class TestDailySummary:
    def test_basic_summary(self):
        result = format_daily_summary(
            date=datetime(2026, 4, 15),
            total_spent=485_000,
            transaction_count=4,
            breakdown=[
                ("food", 245_000),
                ("transport", 150_000),
                ("shopping", 90_000),
            ],
            vs_average_pct=12,
        )
        assert "15/04" in result
        assert "485,000đ" in result
        assert "(4 giao dịch)" in result
        assert "🍜 Ăn uống" in result
        assert "🚗 Di chuyển" in result
        assert "+12%" in result

    def test_negative_vs_average(self):
        result = format_daily_summary(
            date=datetime(2026, 4, 15),
            total_spent=200_000,
            transaction_count=2,
            breakdown=[("food", 200_000)],
            vs_average_pct=-8,
        )
        assert "-8%" in result
        assert "↓" in result

    def test_empty_breakdown(self):
        result = format_daily_summary(
            date=datetime(2026, 4, 15),
            total_spent=0,
            transaction_count=0,
            breakdown=[],
        )
        assert "0đ" in result

    def test_sorts_by_amount_desc(self):
        result = format_daily_summary(
            date=datetime(2026, 4, 15),
            total_spent=500_000,
            transaction_count=3,
            breakdown=[
                ("food", 100_000),
                ("transport", 300_000),
                ("shopping", 100_000),
            ],
        )
        # Transport (largest) should appear before food
        assert result.index("Di chuyển") < result.index("Ăn uống")


class TestBudgetAlert:
    def test_under_limit(self):
        result = format_budget_alert(
            category_code="food",
            spent=500_000,
            budget=1_000_000,
            days_left=10,
        )
        assert "📊" in result
        assert "Còn 500k" in result
        assert "10 ngày" in result

    def test_near_limit(self):
        result = format_budget_alert(
            category_code="food",
            spent=950_000,
            budget=1_000_000,
            days_left=5,
        )
        assert "⚠️" in result
        assert "Sắp chạm trần" in result

    def test_over_limit(self):
        result = format_budget_alert(
            category_code="food",
            spent=1_200_000,
            budget=1_000_000,
            days_left=3,
        )
        assert "🚨" in result
        assert "Đã vượt" in result


class TestWelcomeMessage:
    def test_no_name(self):
        result = format_welcome_message()
        assert "Chào bạn!" in result
        assert "👋" in result

    def test_with_name(self):
        result = format_welcome_message("Phương")
        assert "Chào Phương!" in result

    def test_includes_usage_hints(self):
        result = format_welcome_message()
        assert "45k phở" in result or "ghi giao dịch" in result
