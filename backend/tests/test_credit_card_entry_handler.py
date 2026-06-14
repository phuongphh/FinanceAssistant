import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_show_credit_cards_list_empty_state_omits_delete_button(monkeypatch):
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
    # No delete button when there are no cards — keeps the empty state clean
    callbacks = [btn["callback_data"] for row in rows for btn in row]
    assert "expense:credit:del" not in callbacks
    assert rows[-1][0]["callback_data"] == "menu:expenses"


@pytest.mark.asyncio
async def test_show_credit_cards_list_with_cards_includes_delete_button(monkeypatch):
    from backend.bot.handlers import credit_card_entry

    sent = {}

    async def fake_send_message(**kwargs):
        sent.update(kwargs)

    monkeypatch.setattr(credit_card_entry, "send_message", fake_send_message)
    monkeypatch.setattr(
        "backend.bot.handlers.credit_card_entry.list_credit_cards",
        AsyncMock(return_value=[
            SimpleNamespace(
                id=uuid.uuid4(),
                bank_name="MSB",
                credit_limit=10_000_000,
                debt_balance=1_500_000,
                closing_date=20,
            )
        ]),
    )

    await credit_card_entry.show_credit_cards_list(db=None, chat_id=1, user=SimpleNamespace(id=1))
    rows = sent["reply_markup"]["inline_keyboard"]
    callbacks = [btn["callback_data"] for row in rows for btn in row]
    assert "expense:credit:add" in callbacks
    assert "expense:credit:del" in callbacks
    assert "menu:expenses" in callbacks


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


@pytest.mark.asyncio
async def test_delete_picker_lists_cards_as_buttons(monkeypatch):
    from backend.bot.handlers import credit_card_entry

    card_id = uuid.uuid4()
    sent = {}

    async def fake_send_message(**kwargs):
        sent.update(kwargs)

    monkeypatch.setattr(credit_card_entry, "send_message", fake_send_message)
    monkeypatch.setattr(
        "backend.bot.handlers.credit_card_entry.list_credit_cards",
        AsyncMock(return_value=[SimpleNamespace(id=card_id, bank_name="MSB")]),
    )

    await credit_card_entry.show_credit_card_delete_picker(
        db=None, chat_id=1, user=SimpleNamespace(id=1)
    )
    rows = sent["reply_markup"]["inline_keyboard"]
    assert rows[0][0]["callback_data"] == f"expense:credit:del:pick:{card_id}"
    assert "MSB" in rows[0][0]["text"]
    assert rows[-1][0]["callback_data"] == "menu:expenses:credit_cards"


@pytest.mark.asyncio
async def test_delete_picker_empty_state(monkeypatch):
    from backend.bot.handlers import credit_card_entry

    sent = {}

    async def fake_send_message(**kwargs):
        sent.update(kwargs)

    monkeypatch.setattr(credit_card_entry, "send_message", fake_send_message)
    monkeypatch.setattr(
        "backend.bot.handlers.credit_card_entry.list_credit_cards",
        AsyncMock(return_value=[]),
    )

    await credit_card_entry.show_credit_card_delete_picker(
        db=None, chat_id=1, user=SimpleNamespace(id=1)
    )
    assert "chưa có thẻ" in sent["text"].lower()


@pytest.mark.asyncio
async def test_delete_confirm_shows_two_tap_keyboard(monkeypatch):
    from backend.bot.handlers import credit_card_entry

    card_id = uuid.uuid4()
    sent = {}

    async def fake_send_message(**kwargs):
        sent.update(kwargs)

    monkeypatch.setattr(credit_card_entry, "send_message", fake_send_message)
    monkeypatch.setattr(
        "backend.bot.handlers.credit_card_entry.get_credit_card",
        AsyncMock(return_value=SimpleNamespace(id=card_id, bank_name="MSB")),
    )

    await credit_card_entry.show_credit_card_delete_confirm(
        db=None, chat_id=1, user=SimpleNamespace(id=1), card_id=str(card_id)
    )
    rows = sent["reply_markup"]["inline_keyboard"]
    assert rows[0][0]["text"] == "🗑️ Xóa thật"
    assert rows[0][0]["callback_data"] == f"expense:credit:del:confirm:{card_id}"
    assert rows[1][0]["text"] == "❌ Không, giữ lại"
    assert rows[1][0]["callback_data"] == "expense:credit:del"
    assert "MSB" in sent["text"]


@pytest.mark.asyncio
async def test_delete_confirm_rejects_invalid_card_id(monkeypatch):
    from backend.bot.handlers import credit_card_entry

    sent = {}

    async def fake_send_message(**kwargs):
        sent.update(kwargs)

    monkeypatch.setattr(credit_card_entry, "send_message", fake_send_message)

    await credit_card_entry.show_credit_card_delete_confirm(
        db=None, chat_id=1, user=SimpleNamespace(id=1), card_id="not-a-uuid"
    )
    assert "Không tìm thấy" in sent["text"]


@pytest.mark.asyncio
async def test_delete_confirm_card_already_deleted(monkeypatch):
    from backend.bot.handlers import credit_card_entry

    card_id = uuid.uuid4()
    sent = {}

    async def fake_send_message(**kwargs):
        sent.update(kwargs)

    monkeypatch.setattr(credit_card_entry, "send_message", fake_send_message)
    monkeypatch.setattr(
        "backend.bot.handlers.credit_card_entry.get_credit_card",
        AsyncMock(return_value=None),
    )

    await credit_card_entry.show_credit_card_delete_confirm(
        db=None, chat_id=1, user=SimpleNamespace(id=1), card_id=str(card_id)
    )
    assert "không còn" in sent["text"].lower()


@pytest.mark.asyncio
async def test_confirm_credit_card_delete_soft_deletes_and_refreshes(monkeypatch):
    from backend.bot.handlers import credit_card_entry

    card_id = uuid.uuid4()
    sent: list[dict] = []

    async def fake_send_message(**kwargs):
        sent.append(dict(kwargs))

    delete_mock = AsyncMock(return_value=SimpleNamespace(bank_name="MSB"))
    monkeypatch.setattr(credit_card_entry, "send_message", fake_send_message)
    monkeypatch.setattr(
        "backend.bot.handlers.credit_card_entry.delete_credit_card", delete_mock
    )
    monkeypatch.setattr(
        "backend.bot.handlers.credit_card_entry.list_credit_cards",
        AsyncMock(return_value=[]),
    )

    await credit_card_entry.confirm_credit_card_delete(
        db=None, chat_id=1, user=SimpleNamespace(id=1), card_id=str(card_id)
    )
    delete_mock.assert_awaited_once()
    # First message confirms the deletion, second message re-renders the list
    assert any("Đã xóa thẻ" in m["text"] for m in sent)
    assert any("Thẻ tín dụng" in m["text"] for m in sent)


@pytest.mark.asyncio
async def test_confirm_credit_card_delete_idempotent(monkeypatch):
    from backend.bot.handlers import credit_card_entry

    card_id = uuid.uuid4()
    sent: list[dict] = []

    async def fake_send_message(**kwargs):
        sent.append(dict(kwargs))

    monkeypatch.setattr(credit_card_entry, "send_message", fake_send_message)
    monkeypatch.setattr(
        "backend.bot.handlers.credit_card_entry.delete_credit_card",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "backend.bot.handlers.credit_card_entry.list_credit_cards",
        AsyncMock(return_value=[]),
    )

    await credit_card_entry.confirm_credit_card_delete(
        db=None, chat_id=1, user=SimpleNamespace(id=1), card_id=str(card_id)
    )
    assert any("đã được xóa" in m["text"].lower() for m in sent)


@pytest.mark.asyncio
async def test_confirm_credit_card_delete_rejects_invalid_uuid(monkeypatch):
    from backend.bot.handlers import credit_card_entry

    sent: list[dict] = []

    async def fake_send_message(**kwargs):
        sent.append(dict(kwargs))

    delete_mock = AsyncMock()
    monkeypatch.setattr(credit_card_entry, "send_message", fake_send_message)
    monkeypatch.setattr(
        "backend.bot.handlers.credit_card_entry.delete_credit_card", delete_mock
    )

    await credit_card_entry.confirm_credit_card_delete(
        db=None, chat_id=1, user=SimpleNamespace(id=1), card_id="not-a-uuid"
    )
    # Must not even attempt the DB call when the id is malformed —
    # callback data comes from the wire, treat it as untrusted input.
    delete_mock.assert_not_awaited()
    assert "Không tìm thấy" in sent[0]["text"]
