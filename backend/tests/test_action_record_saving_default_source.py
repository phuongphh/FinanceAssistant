"""Saving intent confirm path must honour ``default_expense_source``.

Mirrors the quick-transaction and OCR paths: any handler that turns user
intent into a persisted expense routes the payload through
``apply_default_source`` before service-level persistence.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.bot.handlers import message as message_handler
from backend.intent import pending_action


def _user():
    u = MagicMock()
    u.id = uuid.uuid4()
    u.telegram_id = 42
    return u


@pytest.mark.asyncio
async def test_action_record_saving_applies_default_source():
    user = _user()
    state = {
        "flow": pending_action.FLOW_PENDING_ACTION,
        "intent": "action_record_saving",
        "parameters": {"amount": 1_000_000},
    }

    async def _stamp(_db, _uid, data):
        data.source_type = "cash"
        return data

    create_expense = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))
    with patch.object(message_handler, "send_message", AsyncMock()), \
         patch.object(message_handler, "apply_default_source",
                       AsyncMock(side_effect=_stamp)) as apply_src, \
         patch.object(message_handler.expense_service, "create_expense",
                       create_expense), \
         patch.object(message_handler, "send_transaction_confirmation",
                       AsyncMock()), \
         patch.object(message_handler.pending_action, "clear", AsyncMock()):
        ok = await message_handler._handle_confirm_callback(
            db=MagicMock(), chat_id=42, user=user, state=state, action="yes"
        )

    assert ok is True
    apply_src.assert_awaited_once()
    create_expense.assert_awaited_once()
    passed = create_expense.await_args.args[2]
    assert passed.source_type == "cash"
