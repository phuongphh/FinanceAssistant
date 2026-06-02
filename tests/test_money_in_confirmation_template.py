"""Tests for money-in rendering in the transaction confirmation template."""

from backend.bot.formatters.templates import format_transaction_confirmation


def test_money_in_confirmation_uses_received_prefix():
    text = format_transaction_confirmation(
        merchant="Lương tháng 6",
        amount=15_000_000,
        category_code="other",
        source_label="Tài khoản thanh toán [Techcombank]",
        show_edit_hint=True,
        transaction_type="money_in",
    )

    assert "💰 Nhận vào: Tài khoản thanh toán [Techcombank]" in text
    # must NOT use the expense "Chi từ" prefix
    assert "Chi từ" not in text
    # money-in edit hint variant
    assert "khoản tiền vào đã được ghi lại" in text


def test_money_in_confirmation_omits_daily_budget_block():
    text = format_transaction_confirmation(
        merchant="Thưởng",
        amount=2_000_000,
        category_code="other",
        source_label="Tiền mặt",
        daily_spent=None,
        daily_budget=None,
        show_edit_hint=True,
        transaction_type="money_in",
    )

    assert "Hôm nay" not in text


def test_expense_confirmation_still_uses_spend_prefix():
    text = format_transaction_confirmation(
        merchant="Phở",
        amount=45000,
        category_code="food",
        source_label="Tiền mặt",
        show_edit_hint=True,
        transaction_type="expense",
    )

    assert "💳 Chi từ: Tiền mặt" in text
    assert "Nhận vào" not in text
    assert "chi tiêu đã được ghi lại" in text
