from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.bot.handlers import callbacks


@pytest.mark.asyncio
async def test_handle_receipt_category_edits_message_with_rerender():
    user = MagicMock()
    rendered = ("new body", {"inline_keyboard": [[{"text": "✓ x"}]]})
    with patch.object(
        callbacks.photo_receipt,
        "set_pending_receipt_category",
        return_value=rendered,
    ) as setcat, \
         patch.object(callbacks, "edit_message_text", AsyncMock()) as edit, \
         patch.object(callbacks, "answer_callback", AsyncMock()) as answer:
        await callbacks._handle_receipt_category(
            db=MagicMock(),
            user=user,
            args=["tok123", "transfer"],
            callback_id="cb1",
            chat_id=999,
            message_id=77,
        )
    setcat.assert_called_once_with(token="tok123", user=user, category="transfer")
    edit.assert_awaited_once_with(
        chat_id=999,
        message_id=77,
        text="new body",
        parse_mode=None,
        reply_markup=rendered[1],
    )
    answer.assert_awaited_once_with("cb1", text="Đã chọn danh mục 👌")


@pytest.mark.asyncio
async def test_handle_receipt_category_expired_alerts_user():
    with patch.object(
        callbacks.photo_receipt,
        "set_pending_receipt_category",
        return_value=None,
    ), \
         patch.object(callbacks, "edit_message_text", AsyncMock()) as edit, \
         patch.object(callbacks, "answer_callback", AsyncMock()) as answer:
        await callbacks._handle_receipt_category(
            db=MagicMock(),
            user=MagicMock(),
            args=["tok123", "transfer"],
            callback_id="cb1",
            chat_id=999,
            message_id=77,
        )
    edit.assert_not_awaited()
    answer.assert_awaited_once()
    assert answer.await_args.kwargs.get("show_alert") is True


@pytest.mark.asyncio
async def test_handle_receipt_category_ignores_malformed_args():
    with patch.object(
        callbacks.photo_receipt, "set_pending_receipt_category"
    ) as setcat, \
         patch.object(callbacks, "edit_message_text", AsyncMock()) as edit, \
         patch.object(callbacks, "answer_callback", AsyncMock()) as answer:
        await callbacks._handle_receipt_category(
            db=MagicMock(),
            user=MagicMock(),
            args=["tok123"],
            callback_id="cb1",
            chat_id=999,
            message_id=77,
        )
    setcat.assert_not_called()
    edit.assert_not_awaited()
    answer.assert_awaited_once_with("cb1")


@pytest.mark.asyncio
async def test_handle_cancel_action_receipt_branch_hides_keyboard():
    with patch.object(callbacks, "edit_message_reply_markup", AsyncMock()) as edit, \
         patch.object(callbacks, "answer_callback", AsyncMock()) as answer:
        await callbacks._handle_cancel_action(
            db=MagicMock(),
            user=MagicMock(),
            args=["receipt", "tok123"],
            callback_id="cb1",
            chat_id=999,
            message_id=77,
        )
    edit.assert_awaited_once_with(
        chat_id=999, message_id=77, reply_markup={"inline_keyboard": []}
    )
    answer.assert_awaited_once_with("cb1", text="Đã huỷ")

