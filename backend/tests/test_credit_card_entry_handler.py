from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_show_credit_cards_list_has_buttons(monkeypatch):
    from backend.bot.handlers import credit_card_entry

    sent = {}

    async def fake_send_message(**kwargs):
        sent.update(kwargs)

    monkeypatch.setattr(credit_card_entry, "send_message", fake_send_message)
    monkeypatch.setattr(
        "backend.bot.handlers.credit_card_entry.list_credit_cards",
        AsyncMock(return_value=[]),
    )

    await credit_card_entry.show_credit_cards_list(db=None, chat_id=1, user=SimpleNamespace(id=1))
    rows = sent["reply_markup"]["inline_keyboard"]
    assert rows[0][0]["callback_data"] == "expense:credit:add"
    assert rows[1][0]["callback_data"] == "menu:expenses"


@pytest.mark.asyncio
async def test_credit_card_wizard_happy_path(monkeypatch):
    from backend.bot.handlers import credit_card_entry

    user = SimpleNamespace(id=1, wizard_state={"flow": credit_card_entry.FLOW_CREDIT_CARD_ADD, "step": "bank_name", "draft": {}})
    sent = []

    async def fake_send_message(*args, **kwargs):
        sent.append(kwargs.get("text") if kwargs else args[1])

    monkeypatch.setattr(credit_card_entry, "send_message", fake_send_message)
    monkeypatch.setattr("backend.bot.handlers.credit_card_entry.get_user_by_telegram_id", AsyncMock(return_value=user), raising=False)

    async def fake_update_step(db, user_id, step, draft_patch):
        user.wizard_state["step"] = step
        user.wizard_state["draft"].update(draft_patch)

    monkeypatch.setattr("backend.bot.handlers.credit_card_entry.wizard_service.update_step", fake_update_step)
    monkeypatch.setattr("backend.bot.handlers.credit_card_entry.wizard_service.clear", AsyncMock())
    monkeypatch.setattr(
        "backend.bot.handlers.credit_card_entry.create_credit_card",
        AsyncMock(return_value=SimpleNamespace(bank_name="MSB", debt_balance=100000000, closing_date=20)),
    )

    msg = {"chat": {"id": 1}, "from": {"id": 1}}
    assert await credit_card_entry.handle_credit_card_text_input(None, {**msg, "text": "MSB"})
    assert await credit_card_entry.handle_credit_card_text_input(None, {**msg, "text": "100tr"})
    assert await credit_card_entry.handle_credit_card_text_input(None, {**msg, "text": "20"})
    assert any("Đã thêm thẻ tín dụng thành công" in s for s in sent)
