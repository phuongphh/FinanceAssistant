"""Tests for the money-in-aware edit pickers on the transaction confirm card.

Money-in transactions must mirror expense's 4 edit buttons but with the
correct taxonomy:
  * the source picker hides credit cards (money can't arrive into a card)
  * the category picker offers income categories (not spending buckets)
"""

from backend.bot.keyboards.transaction_keyboard import (
    category_picker_keyboard,
    source_picker_keyboard,
)
from backend.config.categories import (
    get_all_categories,
    get_all_income_categories,
    get_category,
)


def _all_callback_data(markup: dict) -> list[str]:
    return [
        btn["callback_data"]
        for row in markup["inline_keyboard"]
        for btn in row
    ]


def _all_labels(markup: dict) -> list[str]:
    return [btn["text"] for row in markup["inline_keyboard"] for btn in row]


# --- source picker -------------------------------------------------------


def test_source_picker_expense_includes_credit_card():
    markup = source_picker_keyboard("tx-1")
    assert any("Thẻ tín dụng" in t for t in _all_labels(markup))
    assert any(cb.endswith(":card") for cb in _all_callback_data(markup))


def test_source_picker_money_in_hides_credit_card():
    markup = source_picker_keyboard("tx-1", allow_credit_card=False)
    assert not any("Thẻ tín dụng" in t for t in _all_labels(markup))
    assert not any(cb.endswith(":card") for cb in _all_callback_data(markup))
    # cash / bank / wallet still offered
    cbs = _all_callback_data(markup)
    assert any(cb.endswith(":cash") for cb in cbs)
    assert any(cb.endswith(":bank") for cb in cbs)
    assert any(cb.endswith(":wallet") for cb in cbs)


# --- category picker -----------------------------------------------------


def test_category_picker_expense_uses_spending_buckets():
    labels = " | ".join(_all_labels(category_picker_keyboard("tx-1")))
    spending_names = {c.name_vi for c in get_all_categories()}
    # at least one spending bucket present, no income-only label
    assert any(name in labels for name in spending_names)
    assert "Lương/Thưởng" not in labels


def test_category_picker_money_in_uses_income_categories():
    labels = " | ".join(
        _all_labels(category_picker_keyboard("tx-1", transaction_type="money_in"))
    )
    assert "Lương/Thưởng" in labels
    assert "Cổ tức" in labels
    # only income categories shown, no spending-only bucket
    assert "Ăn uống" not in labels
    for cat in get_all_income_categories():
        assert cat.name_vi in labels


# --- category resolution -------------------------------------------------


def test_get_category_resolves_income_codes():
    assert get_category("salary_bonus").name_vi == "Lương/Thưởng"
    assert get_category("dividend").emoji == "📈"


def test_get_category_unknown_falls_back_to_other():
    assert get_category("nonexistent").code == "other"
