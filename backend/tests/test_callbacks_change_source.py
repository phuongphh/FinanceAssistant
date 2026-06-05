"""Issue #897 — 2-step source edit via inline keyboard."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.bot.handlers import callbacks


@pytest.mark.asyncio
async def test_change_source_one_arg_swaps_to_picker_and_starts_wizard(monkeypatch):
    expense = SimpleNamespace(id="tx-1", transaction_type="expense")

    monkeypatch.setattr(
        callbacks,
        "resolve_transaction_by_callback_id",
        AsyncMock(return_value=expense),
    )
    start_flow = AsyncMock()
    monkeypatch.setattr(callbacks.wizard_service, "start_flow", start_flow)
    edit_markup = AsyncMock()
    monkeypatch.setattr(callbacks, "edit_message_reply_markup", edit_markup)
    answer = AsyncMock()
    monkeypatch.setattr(callbacks, "answer_callback", answer)

    db = SimpleNamespace()
    user = SimpleNamespace(id=42)

    await callbacks._handle_change_source(
        db=db,
        user=user,
        args=["tx-1"],
        callback_id="cb1",
        chat_id=10,
        message_id=20,
    )

    start_flow.assert_awaited_once()
    kwargs = start_flow.await_args.kwargs
    assert kwargs["flow"] == "transaction_source_edit"
    assert kwargs["step"] == "pick_kind"
    assert kwargs["draft"]["expense_id"] == "tx-1"
    edit_markup.assert_awaited_once()
    answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_change_source_cash_applies_immediately(monkeypatch):
    expense = SimpleNamespace(id="tx-1", transaction_type="expense")
    updated = SimpleNamespace(id="tx-1", transaction_type="expense")

    monkeypatch.setattr(
        callbacks,
        "resolve_transaction_by_callback_id",
        AsyncMock(return_value=expense),
    )
    update_expense = AsyncMock(return_value=updated)
    monkeypatch.setattr(callbacks.expense_service, "update_expense", update_expense)
    clear = AsyncMock()
    monkeypatch.setattr(callbacks.wizard_service, "clear", clear)
    rerender = AsyncMock()
    monkeypatch.setattr(callbacks, "_rerender_transaction_message", rerender)
    monkeypatch.setattr(callbacks, "answer_callback", AsyncMock())

    db = SimpleNamespace()
    user = SimpleNamespace(id=42)

    await callbacks._handle_change_source(
        db=db,
        user=user,
        args=["tx-1", "cash"],
        callback_id="cb1",
        chat_id=10,
        message_id=20,
    )

    update_expense.assert_awaited_once()
    update_arg = update_expense.await_args.args[3]
    assert update_arg.source_type == "cash"
    clear.assert_awaited_once()
    rerender.assert_awaited_once_with(10, 20, updated, edited=True, db=db)


@pytest.mark.asyncio
async def test_change_source_wallet_swaps_to_subpicker(monkeypatch):
    expense = SimpleNamespace(id="tx-1", transaction_type="expense")
    monkeypatch.setattr(
        callbacks,
        "resolve_transaction_by_callback_id",
        AsyncMock(return_value=expense),
    )
    wallet_one_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    wallet_two_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    wallets = [
        SimpleNamespace(id=wallet_one_id, name="MoMo cá nhân", subtype="momo"),
        SimpleNamespace(id=wallet_two_id, name="Ví ZaloPay", subtype="e_wallet"),
        SimpleNamespace(
            id="cccccccc-cccc-cccc-cccc-cccccccccccc",
            name="Vietcombank",
            subtype="bank_checking",
        ),
    ]
    monkeypatch.setattr(callbacks, "list_assets", AsyncMock(return_value=wallets))
    edit_markup = AsyncMock()
    monkeypatch.setattr(callbacks, "edit_message_reply_markup", edit_markup)
    monkeypatch.setattr(callbacks, "answer_callback", AsyncMock())

    await callbacks._handle_change_source(
        db=SimpleNamespace(),
        user=SimpleNamespace(id=42),
        args=["tx-1", "wallet"],
        callback_id="cb1",
        chat_id=10,
        message_id=20,
    )
    edit_markup.assert_awaited_once()
    markup = edit_markup.await_args.kwargs["reply_markup"]
    callbacks_data = [
        btn["callback_data"] for row in markup["inline_keyboard"] for btn in row
    ]
    assert f"chsrc_wl:{wallet_one_id}" in callbacks_data
    assert f"chsrc_wl:{wallet_two_id}" in callbacks_data
    # Bank-typed assets must NOT leak into the wallet sub-picker.
    assert not any(cd.startswith("chsrc_wl:cccccccc") for cd in callbacks_data)
    labels = [btn["text"] for row in markup["inline_keyboard"] for btn in row]
    assert any("MoMo cá nhân" in label for label in labels)
    assert any("Ví ZaloPay" in label for label in labels)


@pytest.mark.asyncio
async def test_change_source_wallet_alerts_when_user_has_no_wallets(monkeypatch):
    expense = SimpleNamespace(id="tx-1", transaction_type="expense")
    monkeypatch.setattr(
        callbacks,
        "resolve_transaction_by_callback_id",
        AsyncMock(return_value=expense),
    )
    monkeypatch.setattr(callbacks, "list_assets", AsyncMock(return_value=[]))
    edit_markup = AsyncMock()
    monkeypatch.setattr(callbacks, "edit_message_reply_markup", edit_markup)
    answer = AsyncMock()
    monkeypatch.setattr(callbacks, "answer_callback", answer)

    await callbacks._handle_change_source(
        db=SimpleNamespace(),
        user=SimpleNamespace(id=42),
        args=["tx-1", "wallet"],
        callback_id="cb1",
        chat_id=10,
        message_id=20,
    )

    edit_markup.assert_not_awaited()
    answer.assert_awaited_once()
    assert answer.await_args.kwargs.get("show_alert") is True
    assert "ví điện tử" in answer.await_args.kwargs.get("text", "").lower()


@pytest.mark.asyncio
async def test_change_source_subpicker_applies_wallet_asset(monkeypatch):
    """chsrc_wl:<asset_uuid> resolves to source_type=e_wallet + source_asset_id."""
    expense = SimpleNamespace(id="tx-1", transaction_type="expense")
    updated = SimpleNamespace(id="tx-1", transaction_type="expense")

    user = SimpleNamespace(
        id=42,
        wizard_state={
            "flow": "transaction_source_edit",
            "step": "pick_kind",
            "draft": {"expense_id": "tx-1", "chat_id": 10, "message_id": 20},
        },
    )

    monkeypatch.setattr(
        callbacks, "get_user_by_telegram_id", AsyncMock(return_value=user)
    )
    monkeypatch.setattr(
        callbacks,
        "resolve_transaction_by_callback_id",
        AsyncMock(return_value=expense),
    )
    update_expense = AsyncMock(return_value=updated)
    monkeypatch.setattr(callbacks.expense_service, "update_expense", update_expense)
    clear = AsyncMock()
    monkeypatch.setattr(callbacks.wizard_service, "clear", clear)
    rerender = AsyncMock()
    monkeypatch.setattr(callbacks, "_rerender_transaction_message", rerender)
    monkeypatch.setattr(callbacks, "answer_callback", AsyncMock())

    wallet_uuid = "22222222-2222-2222-2222-222222222222"
    callback_query = {
        "id": "cb1",
        "data": f"chsrc_wl:{wallet_uuid}",
        "from": {"id": 7},
        "message": {"chat": {"id": 10}, "message_id": 20},
    }
    handled = await callbacks._handle_change_source_subpicker(
        SimpleNamespace(), callback_query
    )
    assert handled is True
    update_arg = update_expense.await_args.args[3]
    assert update_arg.source_type == "e_wallet"
    assert str(update_arg.source_asset_id) == wallet_uuid
    assert update_arg.source_credit_card_id is None
    assert update_arg.e_wallet_provider is None
    clear.assert_awaited_once()
    rerender.assert_awaited_once()


@pytest.mark.asyncio
async def test_change_source_subpicker_applies_bank(monkeypatch):
    expense = SimpleNamespace(id="tx-1", transaction_type="expense")
    updated = SimpleNamespace(id="tx-1", transaction_type="expense")

    user = SimpleNamespace(
        id=42,
        wizard_state={
            "flow": "transaction_source_edit",
            "step": "pick_kind",
            "draft": {"expense_id": "tx-1", "chat_id": 10, "message_id": 20},
        },
    )

    monkeypatch.setattr(
        callbacks, "get_user_by_telegram_id", AsyncMock(return_value=user)
    )
    monkeypatch.setattr(
        callbacks,
        "resolve_transaction_by_callback_id",
        AsyncMock(return_value=expense),
    )
    update_expense = AsyncMock(return_value=updated)
    monkeypatch.setattr(callbacks.expense_service, "update_expense", update_expense)
    clear = AsyncMock()
    monkeypatch.setattr(callbacks.wizard_service, "clear", clear)
    rerender = AsyncMock()
    monkeypatch.setattr(callbacks, "_rerender_transaction_message", rerender)
    monkeypatch.setattr(callbacks, "answer_callback", AsyncMock())

    callback_query = {
        "id": "cb1",
        "data": "chsrc_bk:11111111-1111-1111-1111-111111111111",
        "from": {"id": 7},
        "message": {"chat": {"id": 10}, "message_id": 20},
    }
    handled = await callbacks._handle_change_source_subpicker(
        SimpleNamespace(), callback_query
    )
    assert handled is True
    update_arg = update_expense.await_args.args[3]
    assert update_arg.source_type == "bank_account"
    assert str(update_arg.source_asset_id) == "11111111-1111-1111-1111-111111111111"
    clear.assert_awaited_once()
    rerender.assert_awaited_once()
    assert rerender.await_args.args[:3] == (10, 20, updated)
    assert rerender.await_args.kwargs["edited"] is True


@pytest.mark.asyncio
async def test_change_source_subpicker_rejects_when_not_in_flow(monkeypatch):
    user = SimpleNamespace(id=42, wizard_state={"flow": "something_else"})
    monkeypatch.setattr(
        callbacks, "get_user_by_telegram_id", AsyncMock(return_value=user)
    )
    answer = AsyncMock()
    monkeypatch.setattr(callbacks, "answer_callback", answer)

    callback_query = {
        "id": "cb1",
        "data": "chsrc_wl:momo",
        "from": {"id": 7},
        "message": {"chat": {"id": 10}, "message_id": 20},
    }
    handled = await callbacks._handle_change_source_subpicker(
        SimpleNamespace(), callback_query
    )
    assert handled is True
    answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_change_source_subpicker_update_failure_alerts_user(monkeypatch):
    """Issue #948 safety net for the change-source flow: when
    ``update_expense`` raises (e.g. DB check-constraint violation on
    the e_wallet flow), the picker must surface a friendly alert and a
    chat fallback rather than leaving the user staring at a stuck spinner.

    Contract mirrors the create_expense safety net:
      - ``answer_callback`` fires with ``show_alert=True`` and a Bé Tiền-
        tone Vietnamese message.
      - A chat ``send_message`` fallback follows.
      - The wizard state is cleared.
      - The re-render is skipped (no successful update to render).
    """
    expense = SimpleNamespace(id="tx-1", transaction_type="expense")
    user = SimpleNamespace(
        id=42,
        wizard_state={
            "flow": "transaction_source_edit",
            "step": "pick_kind",
            "draft": {"expense_id": "tx-1", "chat_id": 10, "message_id": 20},
        },
    )

    monkeypatch.setattr(
        callbacks, "get_user_by_telegram_id", AsyncMock(return_value=user)
    )
    monkeypatch.setattr(
        callbacks,
        "resolve_transaction_by_callback_id",
        AsyncMock(return_value=expense),
    )
    boom = AsyncMock(side_effect=RuntimeError("simulated IntegrityError"))
    monkeypatch.setattr(callbacks.expense_service, "update_expense", boom)
    clear = AsyncMock()
    monkeypatch.setattr(callbacks.wizard_service, "clear", clear)
    rerender = AsyncMock()
    monkeypatch.setattr(callbacks, "_rerender_transaction_message", rerender)
    answer = AsyncMock()
    monkeypatch.setattr(callbacks, "answer_callback", answer)
    send = AsyncMock()
    monkeypatch.setattr(callbacks, "send_message", send)

    callback_query = {
        "id": "cb1",
        "data": "chsrc_wl:22222222-2222-2222-2222-222222222222",
        "from": {"id": 7},
        "message": {"chat": {"id": 10}, "message_id": 20},
    }
    handled = await callbacks._handle_change_source_subpicker(
        SimpleNamespace(), callback_query
    )

    assert handled is True
    rerender.assert_not_awaited()
    answer.assert_awaited_once()
    assert answer.await_args.kwargs.get("show_alert") is True
    alert_text = (answer.await_args.kwargs.get("text") or "").lower()
    assert "chưa đổi" in alert_text or "không đổi" in alert_text
    send.assert_awaited_once()
    clear.assert_awaited_once()
    assert answer.await_args.kwargs.get("show_alert") is True
