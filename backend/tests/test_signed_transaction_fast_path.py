"""Fast-path tests for the signed / amount-led transaction entry.

Regression for the follow-up to PR #892: when the user has configured a
``default_expense_source``, the ``+/-`` or amount-led typed text MUST
skip the source-picker wizard and create the expense directly (mirroring
the LLM-fallback path). When no default is configured, the wizard
remains as a graceful fallback.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.bot.handlers import message as message_handler


def _fake_user():
    user = MagicMock()
    user.id = "user-1"
    user.telegram_id = 555
    return user


def _fake_db():
    db = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.execute = AsyncMock()
    db.get = AsyncMock(return_value=None)
    db.add = MagicMock()
    return db


@pytest.mark.asyncio
async def test_amount_led_expense_uses_default_source_when_set():
    """``45k phở`` with a default source must NOT pop the wizard — it
    should create the expense and send the confirmation card directly.
    """
    db = _fake_db()
    user = _fake_user()
    message = {"chat": {"id": 555}, "from": {"id": 555}, "text": "45k phở"}

    fake_expense = MagicMock(user_id="user-1")

    async def fake_apply_default_source(_db, _uid, data):
        return data.model_copy(update={"source_type": "cash"})

    with patch(
        "backend.bot.handlers.message.get_user_by_telegram_id",
        AsyncMock(return_value=user),
    ), patch(
        "backend.bot.handlers.message.report_service.is_report_query",
        return_value=False,
    ), patch(
        "backend.bot.handlers.message.apply_default_source",
        side_effect=fake_apply_default_source,
    ), patch(
        "backend.bot.handlers.message.expense_service.create_expense",
        AsyncMock(return_value=fake_expense),
    ) as mock_create, patch(
        "backend.bot.handlers.message.send_transaction_confirmation",
        AsyncMock(),
    ) as mock_confirm, patch(
        "backend.bot.handlers.message._start_source_prompt",
        AsyncMock(return_value=True),
    ) as mock_wizard:
        ok = await message_handler.handle_text_message(db, message)

    assert ok is True
    mock_create.assert_awaited_once()
    mock_confirm.assert_awaited_once()
    mock_wizard.assert_not_called()
    expense_data = mock_create.call_args.args[2]
    assert expense_data.amount == 45_000.0
    assert expense_data.category == "other"
    assert expense_data.source_type == "cash"


@pytest.mark.asyncio
async def test_amount_led_expense_falls_back_to_wizard_when_no_default():
    """Without a configured default source, the wizard must still run."""
    db = _fake_db()
    user = _fake_user()
    message = {"chat": {"id": 555}, "from": {"id": 555}, "text": "45k phở"}

    async def fake_apply_default_source(_db, _uid, data):
        return data  # unchanged → no default configured

    with patch(
        "backend.bot.handlers.message.get_user_by_telegram_id",
        AsyncMock(return_value=user),
    ), patch(
        "backend.bot.handlers.message.report_service.is_report_query",
        return_value=False,
    ), patch(
        "backend.bot.handlers.message.apply_default_source",
        side_effect=fake_apply_default_source,
    ), patch(
        "backend.bot.handlers.message.expense_service.create_expense",
        AsyncMock(),
    ) as mock_create, patch(
        "backend.bot.handlers.message.send_transaction_confirmation",
        AsyncMock(),
    ) as mock_confirm, patch(
        "backend.bot.handlers.message._start_source_prompt",
        AsyncMock(return_value=True),
    ) as mock_wizard:
        ok = await message_handler.handle_text_message(db, message)

    assert ok is True
    mock_create.assert_not_called()
    mock_confirm.assert_not_called()
    mock_wizard.assert_awaited_once()


@pytest.mark.asyncio
async def test_money_in_always_uses_wizard():
    """Money-in (+) keeps the existing source-picker wizard regardless
    of the ``default_expense_source`` setting (only expense flows changed).
    """
    db = _fake_db()
    user = _fake_user()
    message = {"chat": {"id": 555}, "from": {"id": 555}, "text": "+5tr lương"}

    async def fake_apply_default_source(_db, _uid, data):
        return data.model_copy(update={"source_type": "cash"})

    with patch(
        "backend.bot.handlers.message.get_user_by_telegram_id",
        AsyncMock(return_value=user),
    ), patch(
        "backend.bot.handlers.message.report_service.is_report_query",
        return_value=False,
    ), patch(
        "backend.bot.handlers.message.apply_default_source",
        side_effect=fake_apply_default_source,
    ), patch(
        "backend.bot.handlers.message.expense_service.create_expense",
        AsyncMock(),
    ) as mock_create, patch(
        "backend.bot.handlers.message.send_transaction_confirmation",
        AsyncMock(),
    ), patch(
        "backend.bot.handlers.message._start_source_prompt",
        AsyncMock(return_value=True),
    ) as mock_wizard:
        ok = await message_handler.handle_text_message(db, message)

    assert ok is True
    mock_create.assert_not_called()
    mock_wizard.assert_awaited_once()
