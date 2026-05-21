"""Unit tests for ``_parse_signed_transaction`` regex narrowing.

Covers the release-6 fix that prevents casual chat or question-shaped
inputs from being hijacked into the expense fast-path while preserving
the two legitimate entry forms: explicit-sign (`+200k` / `-200k cafe`)
and amount-led (`200k cafe`).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture(scope="module")
def parse():
    # Stub out heavy backend imports the module pulls in at import time
    # so the test stays focused on regex behaviour.
    fake = MagicMock()
    for name in (
        "backend.bot.handlers.free_form_text",
        "backend.bot.handlers.transaction",
        "backend.bot.keyboards.transaction_keyboard",
        "backend.intent",
        "backend.intent.dispatcher",
        "backend.intent.intents",
        "backend.intent.pending_action",
        "backend.schemas.expense",
        "backend.services",
        "backend.services.dashboard_service",
        "backend.services.llm_service",
        "backend.services.telegram_service",
        "backend.services.expense_service",
        "backend.services.report_service",
        "backend.services.wizard_service",
        "backend.wealth.amount_parser",
        "sqlalchemy.ext.asyncio",
    ):
        sys.modules.setdefault(name, fake)

    # parse_amount is the only helper called from the parser; provide a
    # tiny VN-friendly implementation so the test doesn't need the full
    # wealth module.
    from decimal import Decimal

    def parse_amount(s: str):
        s = s.lower().replace(" ", "")
        mult = 1
        for suf, m in (
            ("tỷ", 1_000_000_000), ("ty", 1_000_000_000), ("tỉ", 1_000_000_000),
            ("triệu", 1_000_000), ("trieu", 1_000_000), ("tr", 1_000_000),
            ("nghìn", 1_000), ("nghin", 1_000), ("ngàn", 1_000), ("ngan", 1_000), ("k", 1_000),
        ):
            if s.endswith(suf):
                s = s[: -len(suf)]
                mult = m
                break
        s = s.replace(",", ".")
        try:
            return Decimal(s) * mult
        except Exception:
            return None

    sys.modules["backend.wealth.amount_parser"].parse_amount = parse_amount

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from backend.bot.handlers.message import _parse_signed_transaction

    return _parse_signed_transaction


@pytest.mark.parametrize(
    "text",
    [
        "+200k",
        "-200k cafe",
        "+1.5tr lương",
        "-50000 ăn trưa",
    ],
)
def test_signed_forms_are_parsed(parse, text):
    assert parse(text) is not None


@pytest.mark.parametrize(
    "text",
    [
        "200k cafe",
        "50000 ăn trưa",
        "1,5 triệu lương",
    ],
)
def test_amount_led_forms_are_parsed(parse, text):
    assert parse(text) is not None


@pytest.mark.parametrize(
    "text",
    [
        # Casual chat that happens to mention an amount — must NOT hijack.
        "hello 200k there",
        "nhắc tôi mua sữa 50k chiều mai",
        # Question-shaped inputs.
        "200 nghìn là bao nhiêu USD",
        "200k là gì",
        "khi nào tôi có 1 tỷ",
        # Ambiguous bare digits.
        "200",
        # Pure chat without any amount.
        "hello world",
    ],
)
def test_non_transaction_inputs_are_rejected(parse, text):
    assert parse(text) is None


def test_signed_money_in_direction(parse):
    parsed = parse("+200k lương tháng 5")
    assert parsed is not None
    assert parsed["transaction_type"] == "money_in"


def test_signed_expense_direction(parse):
    parsed = parse("-200k cafe")
    assert parsed is not None
    assert parsed["transaction_type"] == "expense"
