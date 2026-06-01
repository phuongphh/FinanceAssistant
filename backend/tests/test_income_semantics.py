"""Unit tests for the shared income/expense semantics module.

This module is the single source of truth that the message-layer
fast-path, the rule-based tier, and the expense handler all rely on.
The headline case is **"được bố cho 500k"** — a money-in gift that used
to be silently mis-recorded as an expense because the diacritic-stripped
"duoc bo cho" broke the old "duoc cho" substring match.
"""

from __future__ import annotations

import pytest

from backend.intent.income_semantics import (
    has_leading_plus_sign,
    is_duoc_money_in,
    looks_like_income,
    looks_like_wallet_topup,
)


@pytest.mark.parametrize(
    "text",
    [
        "được bố cho 500k",
        "được mẹ cho 1tr",
        "được thưởng 200k",
        "được lì xì 50k trên momo",
        "được mừng tuổi 100k",
        "được biếu 2tr",
        "được sếp thưởng 5tr",
        "được công ty hỗ trợ 3tr",
        # Refunds are money-IN even though they reference the original
        # purchase ("mua") — the spend keyword must not veto them.
        "được hoàn tiền 200k do mua hàng lỗi",
        "được hoàn 200k tiền mua vé",
        # Found money: cash picked up is money-in even though "tìm/nhặt
        # được" is a resultative verb — the amount sits right after "được".
        "tìm được 200k dưới gối",
        "nhặt được 50k ngoài đường",
        "lượm được 100k",
        # tone-less typing must behave identically
        "duoc bo cho 500k",
        "duoc li xi 50k",
        "tim duoc 200k duoi goi",
    ],
)
def test_duoc_money_in_positive(text: str) -> None:
    assert is_duoc_money_in(text) is True
    assert looks_like_income(text) is True


@pytest.mark.parametrize(
    "text",
    [
        # Resultative "được" = managed to <verb> → EXPENSE, not income.
        "mua được áo 200k",
        "mua được cho con đôi giày 300k",
        "tìm được quán ăn ngon 150k",
        # Question shapes must never be recordable transactions.
        "được thưởng bao nhiêu?",
        "lì xì khi nào được nhận",
        # Mixed sentence with a spend verb → expense reading wins.
        "được thưởng 5tr rồi tiêu hết",
        "được cho 1tr nhưng mua quà hết",
        # A refund that is then re-spent flips back to expense.
        "được hoàn 200k rồi tiêu hết",
        # Found an OBJECT worth X (an item, not cash) — no money moved and
        # no "buy" action yet, so it is NOT a transaction. The amount comes
        # AFTER the object noun, not directly after "được".
        "tìm được thắt lưng 500k",
        "nhặt được cái ví 2tr",
        "tìm được quán ngon 150k",
        # No giving verb following "được".
        "được rồi để mai tính",
        "hôm nay được nghỉ",
        "",
    ],
)
def test_duoc_money_in_negative(text: str) -> None:
    assert is_duoc_money_in(text) is False


def test_leading_plus_sign() -> None:
    assert has_leading_plus_sign("+200k") is True
    assert has_leading_plus_sign("  + 5tr thưởng") is True
    assert has_leading_plus_sign("-200k") is False
    assert has_leading_plus_sign("200k cà phê") is False
    assert has_leading_plus_sign("") is False


def test_wallet_topup() -> None:
    assert looks_like_wallet_topup("thêm 3tr vào ví momo") is True
    assert looks_like_wallet_topup("nạp 500k vào tài khoản VCB") is True
    assert looks_like_wallet_topup("50k cà phê") is False


@pytest.mark.parametrize(
    "text,expected",
    [
        # Income phrasings.
        ("nhận lương 20tr", True),
        ("được thưởng 200k", True),
        ("được bố cho 500k", True),
        ("+200k tiền tip", True),
        ("thêm 3tr vào ví momo", True),
        # Expense phrasings.
        ("50k cà phê", False),
        ("-200k taxi", False),
        ("mua sách 200k", False),
        # Diacritic-collision guards: bare "thường" (usually) and bare
        # "trả tiền" must NOT be read as income.
        ("mình thường mua cà phê 35k", False),
        ("thường ăn sáng 50k", False),
        # Mixed: salary mentioned but spent → expense wins.
        ("lương tháng này tiêu hết 5tr", False),
        # "công ty trả lương 20tr" — paying salary is income to the user.
        ("công ty trả lương 20tr", True),
        # Lucky money WITHOUT a receiving cue = the user is GIVING it →
        # expense, not income.
        ("lì xì cháu 500k", False),
        ("mừng tuổi cho con 100k", False),
        # ...but a receiving cue ("nhận"/"được") makes it income.
        ("nhận lì xì 500k", True),
        ("được mừng tuổi 100k", True),
        # Refund inflow that names the original purchase is still income.
        ("được hoàn 200k tiền mua vé", True),
        # Found money is income; a found object (worth X) is not.
        ("tìm được 200k dưới gối", True),
        ("tìm được thắt lưng 500k", False),
    ],
)
def test_looks_like_income(text: str, expected: bool) -> None:
    assert looks_like_income(text) is expected
