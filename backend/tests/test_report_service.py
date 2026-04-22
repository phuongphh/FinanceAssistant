"""Tests for report_service — intent detection, month parsing, and orchestration."""
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.report_service import extract_month_key, is_report_query, process_report_request


class TestIsReportQuery:
    def test_detects_bao_cao(self):
        assert is_report_query("báo cáo tháng này") is True

    def test_detects_tong_chi_tieu_lowercase(self):
        assert is_report_query("tổng chi tiêu") is True

    def test_detects_tong_chi_tieu_capitalized(self):
        # User sent "Tổng chi tiêu" from the menu prompt — must match
        assert is_report_query("Tổng chi tiêu") is True

    def test_detects_chi_tieu_thang(self):
        assert is_report_query("chi tiêu tháng này bao nhiêu?") is True

    def test_detects_xai_bao_nhieu(self):
        assert is_report_query("tôi xài bao nhiêu tháng 3?") is True

    def test_detects_english_report(self):
        assert is_report_query("spending this month") is True

    def test_detects_english_report_keyword(self):
        assert is_report_query("show me a report") is True

    def test_detects_da_chi(self):
        assert is_report_query("tháng này tôi đã chi bao nhiêu") is True

    def test_does_not_match_plain_expense_entry(self):
        assert is_report_query("ăn trưa 50k") is False

    def test_does_not_match_amount_only(self):
        assert is_report_query("150000") is False

    def test_does_not_match_empty_string(self):
        assert is_report_query("") is False

    def test_does_not_match_menu_command(self):
        assert is_report_query("menu") is False

    def test_does_not_match_greeting(self):
        assert is_report_query("xin chào") is False


class TestExtractMonthKey:
    def test_defaults_to_current_month(self):
        today = date.today()
        assert extract_month_key("tổng chi tiêu") == today.strftime("%Y-%m")

    def test_empty_text_defaults_to_current_month(self):
        today = date.today()
        assert extract_month_key("") == today.strftime("%Y-%m")

    def test_previous_month_mid_year(self):
        with patch("backend.services.report_service.date") as mock_date:
            mock_date.today.return_value = date(2026, 4, 22)
            result = extract_month_key("báo cáo tháng trước")
        assert result == "2026-03"

    def test_previous_month_january_wraps_to_december(self):
        with patch("backend.services.report_service.date") as mock_date:
            mock_date.today.return_value = date(2026, 1, 15)
            result = extract_month_key("tháng trước")
        assert result == "2025-12"

    def test_specific_month_in_past(self):
        with patch("backend.services.report_service.date") as mock_date:
            mock_date.today.return_value = date(2026, 4, 22)
            result = extract_month_key("báo cáo tháng 3")
        assert result == "2026-03"

    def test_specific_month_in_future_uses_previous_year(self):
        with patch("backend.services.report_service.date") as mock_date:
            mock_date.today.return_value = date(2026, 4, 22)
            result = extract_month_key("báo cáo tháng 12")
        assert result == "2025-12"

    def test_specific_month_current_month(self):
        with patch("backend.services.report_service.date") as mock_date:
            mock_date.today.return_value = date(2026, 4, 22)
            result = extract_month_key("tháng 4")
        assert result == "2026-04"

    def test_explicit_year_month_format(self):
        result = extract_month_key("báo cáo 2026-03 cho tôi")
        assert result == "2026-03"

    def test_explicit_year_month_no_surrounding_text(self):
        result = extract_month_key("2025-11")
        assert result == "2025-11"

    def test_thang_truoc_unaccented(self):
        with patch("backend.services.report_service.date") as mock_date:
            mock_date.today.return_value = date(2026, 4, 22)
            result = extract_month_key("thang truoc")
        assert result == "2026-03"


class TestProcessReportRequest:
    @pytest.mark.asyncio
    async def test_returns_not_registered_when_no_user(self):
        db = AsyncMock()
        with patch("backend.services.report_service.get_user_by_telegram_id", return_value=None):
            result = await process_report_request(db, telegram_id=12345, text="báo cáo")
        assert "chưa đăng ký" in result

    @pytest.mark.asyncio
    async def test_returns_report_text_on_success(self):
        db = AsyncMock()
        mock_user = MagicMock()
        mock_user.id = "user-uuid"
        mock_report = MagicMock()
        mock_report.report_text = "📊 Báo cáo tháng 4: bạn đã chi 5,000,000 VND"

        with patch("backend.services.report_service.get_user_by_telegram_id", return_value=mock_user), \
             patch("backend.services.report_service.generate_monthly_report", return_value=mock_report):
            result = await process_report_request(db, telegram_id=99, text="tổng chi tiêu")

        assert result == mock_report.report_text

    @pytest.mark.asyncio
    async def test_returns_fallback_text_when_report_text_is_none(self):
        db = AsyncMock()
        mock_user = MagicMock()
        mock_user.id = "user-uuid"
        mock_report = MagicMock()
        mock_report.report_text = None

        with patch("backend.services.report_service.get_user_by_telegram_id", return_value=mock_user), \
             patch("backend.services.report_service.generate_monthly_report", return_value=mock_report):
            result = await process_report_request(db, telegram_id=99, text="")

        assert "Không có dữ liệu" in result

    @pytest.mark.asyncio
    async def test_returns_error_string_on_exception(self):
        db = AsyncMock()
        mock_user = MagicMock()
        mock_user.id = "user-uuid"

        with patch("backend.services.report_service.get_user_by_telegram_id", return_value=mock_user), \
             patch("backend.services.report_service.generate_monthly_report", side_effect=RuntimeError("db down")):
            result = await process_report_request(db, telegram_id=99, text="báo cáo")

        assert "Không thể tổng hợp" in result

    @pytest.mark.asyncio
    async def test_passes_extracted_month_to_generate(self):
        db = AsyncMock()
        mock_user = MagicMock()
        mock_user.id = "user-uuid"
        mock_report = MagicMock()
        mock_report.report_text = "ok"

        with patch("backend.services.report_service.get_user_by_telegram_id", return_value=mock_user), \
             patch("backend.services.report_service.generate_monthly_report", return_value=mock_report) as mock_gen, \
             patch("backend.services.report_service.date") as mock_date:
            mock_date.today.return_value = date(2026, 4, 22)
            await process_report_request(db, telegram_id=99, text="báo cáo tháng trước")

        mock_gen.assert_called_once_with(db, mock_user.id, "2026-03")
