from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.bot.handlers import callbacks


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

