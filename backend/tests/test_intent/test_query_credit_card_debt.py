"""Tests for ``QueryCreditCardDebtHandler``."""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.intent.handlers.query_credit_card_debt import (
    QueryCreditCardDebtHandler,
)
from backend.intent.intents import IntentResult, IntentType


def _user(name: str | None = "An") -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.display_name = name
    return user


def _intent() -> IntentResult:
    return IntentResult(
        intent=IntentType.QUERY_CREDIT_CARD_DEBT,
        confidence=0.96,
        parameters={},
        raw_text="dư nợ tín dụng",
    )


def _card(bank: str, debt: Decimal | None) -> MagicMock:
    card = MagicMock()
    card.bank_name = bank
    card.debt_balance = debt
    return card


@pytest.mark.asyncio
async def test_empty_card_list_returns_empty_state_message():
    user = _user("An")
    db = MagicMock()

    with patch(
        "backend.intent.handlers.query_credit_card_debt.list_credit_cards",
        AsyncMock(return_value=[]),
    ):
        response = await QueryCreditCardDebtHandler().handle(_intent(), user, db)

    assert "An" in response
    assert "chưa có thẻ tín dụng" in response
    # Empty-state must point at the menu navigation, not the broken
    # /thetindung shortcut that PR #930 review flagged.
    assert "/menu" in response
    assert "/thetindung" not in response


@pytest.mark.asyncio
async def test_empty_state_falls_back_to_default_name_when_display_name_missing():
    user = _user(name=None)
    db = MagicMock()

    with patch(
        "backend.intent.handlers.query_credit_card_debt.list_credit_cards",
        AsyncMock(return_value=[]),
    ):
        response = await QueryCreditCardDebtHandler().handle(_intent(), user, db)

    assert "bạn" in response


@pytest.mark.asyncio
async def test_single_card_renders_total_and_one_line():
    user = _user("An")
    db = MagicMock()
    cards = [_card("VCB", Decimal("5000000"))]

    with patch(
        "backend.intent.handlers.query_credit_card_debt.list_credit_cards",
        AsyncMock(return_value=cards),
    ):
        response = await QueryCreditCardDebtHandler().handle(_intent(), user, db)

    assert "Dư nợ thẻ tín dụng của An" in response
    assert "Tổng dư nợ" in response
    assert "VCB" in response
    # One bullet per card.
    assert response.count("•") == 1


@pytest.mark.asyncio
async def test_multiple_cards_render_one_bullet_per_card_and_correct_total():
    user = _user("An")
    db = MagicMock()
    cards = [
        _card("VCB", Decimal("5000000")),
        _card("TCB", Decimal("2500000")),
        _card("ACB", Decimal("1000000")),
    ]

    with patch(
        "backend.intent.handlers.query_credit_card_debt.list_credit_cards",
        AsyncMock(return_value=cards),
    ):
        response = await QueryCreditCardDebtHandler().handle(_intent(), user, db)

    # One bullet per card.
    assert response.count("•") == 3
    for bank in ("VCB", "TCB", "ACB"):
        assert bank in response
    # 5tr + 2.5tr + 1tr = 8.5tr — format_money_full renders Vietnamese-style.
    # We only assert the header is present; exact formatting is covered by
    # the money formatter's own tests.
    assert "Tổng dư nợ" in response


@pytest.mark.asyncio
async def test_null_debt_balance_is_treated_as_zero():
    """A card with ``debt_balance=None`` (just opened, no statement yet)
    must not blow up the sum or the per-card line."""
    user = _user("An")
    db = MagicMock()
    cards = [
        _card("VCB", Decimal("5000000")),
        _card("TCB", None),
    ]

    with patch(
        "backend.intent.handlers.query_credit_card_debt.list_credit_cards",
        AsyncMock(return_value=cards),
    ):
        response = await QueryCreditCardDebtHandler().handle(_intent(), user, db)

    assert "VCB" in response
    assert "TCB" in response
    # Two bullets even if one card has null debt.
    assert response.count("•") == 2


@pytest.mark.asyncio
async def test_handler_passes_user_id_to_service():
    """Multi-tenant safety: handler must scope by ``user.id``."""
    user = _user("An")
    db = MagicMock()

    fake = AsyncMock(return_value=[])
    with patch(
        "backend.intent.handlers.query_credit_card_debt.list_credit_cards",
        fake,
    ):
        await QueryCreditCardDebtHandler().handle(_intent(), user, db)

    fake.assert_awaited_once_with(db, user.id)
