"""Tests for the money-in fast-path in message handling.

``_record_transaction_with_default`` creates a money-in transaction with
the user's ``default_money_in_source`` and sends the rich confirmation,
returning False (falling back to the picker) when no default is set.
"""

import uuid
from types import SimpleNamespace

import pytest

from backend.bot.handlers import message as message_handler
from backend.bot.handlers.message import _parse_duoc_money_in


class TestDuocMoneyInAmountScaling:
    """Regression for the ×1,000,000 money-in scaling bug.

    "Vừa được cho 199999 trên momo" was booked as 199,999,000,000đ because
    the amount regex matched "199999 tr" — the "tr" of "trên" — and read it
    as the triệu unit. A unit abbreviation must never glue onto the prefix
    of an ordinary word.
    """

    def test_word_starting_with_unit_does_not_inflate_amount(self):
        # The exact message from the bug report. "199999" carries no real
        # unit, so the strict được-fast-path declines (returns None) and the
        # message falls through to the intent pipeline — crucially it is NOT
        # booked as 199,999,000,000đ.
        assert _parse_duoc_money_in("Vừa được cho 199999 trên momo") is None

    @pytest.mark.parametrize(
        "text",
        [
            "được bố cho 100 trên bàn",  # "tr" in "trên"
            "được mẹ cho 50 kem",  # "k" in "kem"
        ],
    )
    def test_unit_prefixed_words_never_booked(self, text):
        assert _parse_duoc_money_in(text) is None

    @pytest.mark.parametrize(
        "text,expected_amount",
        [
            # Real units must still parse — the fix is surgical.
            ("được bố cho 500k", 500_000.0),
            ("được lì xì 50 ngàn", 50_000.0),
            ("được thưởng 2tr", 2_000_000.0),
            ("được bố cho 1.000.000", 1_000_000.0),
        ],
    )
    def test_real_units_still_record(self, text, expected_amount):
        parsed = _parse_duoc_money_in(text)
        assert parsed is not None, f"fast-path declined a real money-in: {text!r}"
        assert parsed["amount"] == expected_amount
        assert parsed["transaction_type"] == "money_in"


@pytest.mark.asyncio
async def test_record_money_in_with_default_creates_and_confirms(monkeypatch):
    user = SimpleNamespace(id=uuid.uuid4())
    captured = {}

    async def fake_apply_default(_db, _uid, data):
        # simulate default applied → source resolved
        return data.model_copy(update={"source_type": "cash"})

    async def fake_create(_db, _uid, data):
        created = SimpleNamespace(
            transaction_type=data.transaction_type, source_type=data.source_type
        )
        captured["created"] = created
        return created

    async def fake_confirm(_db, expense):
        captured["confirmed"] = expense

    monkeypatch.setattr(message_handler, "apply_default_source", fake_apply_default)
    monkeypatch.setattr(
        message_handler.expense_service, "create_expense", fake_create
    )
    monkeypatch.setattr(
        message_handler, "send_transaction_confirmation", fake_confirm
    )

    parsed = {"amount": 5_000_000, "transaction_type": "money_in", "note": "Lương"}
    ok = await message_handler._record_transaction_with_default(None, user, parsed)

    assert ok is True
    assert captured["created"].transaction_type == "money_in"
    assert captured["created"].source_type == "cash"
    assert captured["confirmed"] is captured["created"]


@pytest.mark.asyncio
async def test_money_in_fastpath_leaves_category_for_income_normalization(monkeypatch):
    """Money-in must reach create_expense at the schema default (needs_review)
    so the service normalizes it to the 'income' category — not 'other'."""
    user = SimpleNamespace(id=uuid.uuid4())
    captured = {}

    async def fake_apply_default(_db, _uid, data):
        captured["category"] = data.category
        return data.model_copy(update={"source_type": "cash"})

    async def fake_create(_db, _uid, data):
        return SimpleNamespace(
            transaction_type=data.transaction_type, source_type=data.source_type
        )

    async def fake_confirm(_db, _expense):
        return None

    monkeypatch.setattr(message_handler, "apply_default_source", fake_apply_default)
    monkeypatch.setattr(message_handler.expense_service, "create_expense", fake_create)
    monkeypatch.setattr(message_handler, "send_transaction_confirmation", fake_confirm)

    parsed = {"amount": 3_000_000, "transaction_type": "money_in", "note": "Thưởng"}
    await message_handler._record_transaction_with_default(None, user, parsed)

    # not forced to "other" — left at the default so create_expense → income
    assert captured["category"] == "needs_review"


@pytest.mark.asyncio
async def test_expense_fastpath_still_hardcodes_other_category(monkeypatch):
    """Regression: the expense fast-path keeps its 'other' category (no LLM)."""
    user = SimpleNamespace(id=uuid.uuid4())
    captured = {}

    async def fake_apply_default(_db, _uid, data):
        captured["category"] = data.category
        return data.model_copy(update={"source_type": "cash"})

    async def fake_create(_db, _uid, data):
        return SimpleNamespace(
            transaction_type=data.transaction_type, source_type=data.source_type
        )

    async def fake_confirm(_db, _expense):
        return None

    monkeypatch.setattr(message_handler, "apply_default_source", fake_apply_default)
    monkeypatch.setattr(message_handler.expense_service, "create_expense", fake_create)
    monkeypatch.setattr(message_handler, "send_transaction_confirmation", fake_confirm)

    parsed = {"amount": 45_000, "transaction_type": "expense", "merchant": "Phở"}
    await message_handler._record_transaction_with_default(None, user, parsed)

    assert captured["category"] == "other"


@pytest.mark.asyncio
async def test_record_money_in_without_default_returns_false(monkeypatch):
    user = SimpleNamespace(id=uuid.uuid4())

    async def fake_apply_default(_db, _uid, data):
        # no default configured → source stays unresolved
        return data

    created = False

    async def fake_create(_db, _uid, data):
        nonlocal created
        created = True
        return SimpleNamespace()

    monkeypatch.setattr(message_handler, "apply_default_source", fake_apply_default)
    monkeypatch.setattr(
        message_handler.expense_service, "create_expense", fake_create
    )

    parsed = {"amount": 5_000_000, "transaction_type": "money_in"}
    ok = await message_handler._record_transaction_with_default(None, user, parsed)

    assert ok is False
    assert created is False  # never reached the create call
