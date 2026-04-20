"""Central callback router for Telegram inline keyboard taps.

Webhook JSON arrives as:

    {
      "callback_query": {
        "id": "...",
        "from": {"id": 1234, ...},
        "message": {"message_id": 42, "chat": {"id": -100...}, ...},
        "data": "change_cat:<uuid>"
      }
    }

Handlers dispatch by prefix, resolve the current user, act on the DB,
and edit the triggering message in place.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend import analytics
from backend.bot.formatters.templates import format_transaction_confirmation
from backend.bot.handlers.transaction import (
    _normalize_category,
    resolve_transaction_by_callback_id,
)
from backend.bot.keyboards.common import CallbackPrefix, parse_callback
from backend.bot.keyboards.transaction_keyboard import (
    category_picker_keyboard,
    confirm_delete_keyboard,
    transaction_actions_keyboard,
)
from backend.models.expense import Expense
from backend.models.user import User
from backend.services import expense_service
from backend.services.telegram_service import (
    answer_callback,
    edit_message_reply_markup,
    edit_message_text,
)

logger = logging.getLogger(__name__)

UNDO_WINDOW_SECONDS = 5


async def _get_user_by_telegram_id(
    db: AsyncSession, telegram_id: int
) -> User | None:
    stmt = select(User).where(
        User.telegram_id == telegram_id,
        User.deleted_at.is_(None),
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _rerender_transaction_message(
    chat_id: int,
    message_id: int,
    expense: Expense,
) -> None:
    text = format_transaction_confirmation(
        merchant=expense.merchant or expense.note or "Giao dịch",
        amount=float(expense.amount),
        category_code=_normalize_category(expense.category),
        time=expense.created_at,
    )
    await edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=text,
        parse_mode="HTML",
        reply_markup=transaction_actions_keyboard(str(expense.id)),
    )


async def handle_transaction_callback(
    db: AsyncSession, callback_query: dict[str, Any]
) -> bool:
    """Entry point for `callback_query` payloads from Telegram webhooks.

    Returns True if the callback matched a transaction-related prefix and
    was handled (caller can then stop further routing).
    """
    data: str = callback_query.get("data", "")
    if not data:
        return False

    prefix, args = parse_callback(data)

    handlers = {
        CallbackPrefix.CHANGE_CATEGORY: _handle_change_category,
        CallbackPrefix.DELETE_TRANSACTION: _handle_delete_transaction,
        CallbackPrefix.CONFIRM_ACTION: _handle_confirm_action,
        CallbackPrefix.CANCEL_ACTION: _handle_cancel_action,
        CallbackPrefix.UNDO_TRANSACTION: _handle_undo_transaction,
        CallbackPrefix.EDIT_TRANSACTION: _handle_edit_transaction,
    }

    handler = handlers.get(prefix)
    if not handler:
        return False

    callback_id = callback_query["id"]
    from_user = callback_query.get("from") or {}
    telegram_id = from_user.get("id")
    message = callback_query.get("message") or {}
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")

    user = await _get_user_by_telegram_id(db, telegram_id) if telegram_id else None

    analytics.track(
        analytics.EventType.BUTTON_TAPPED,
        user_id=user.id if user else None,
        properties={"button": prefix, "has_args": bool(args)},
    )
    if not user:
        await answer_callback(
            callback_id,
            text="Chưa thấy bạn trong danh sách — gõ /start để mình chào nhé 🌱",
            show_alert=True,
        )
        return True

    try:
        await handler(
            db=db,
            user=user,
            args=args,
            callback_id=callback_id,
            chat_id=chat_id,
            message_id=message_id,
        )
    except Exception:
        logger.exception("callback handler failed for %s", data)
        await answer_callback(
            callback_id,
            text="Có gì đó không ổn — bạn thử lại giúp mình?",
            show_alert=True,
        )
    return True


async def _handle_change_category(
    *, db, user, args, callback_id, chat_id, message_id
):
    """2-step flow: show picker → update DB + re-render message."""
    if not args:
        await answer_callback(callback_id, text="Hmm, thiếu thông tin giao dịch — thử tap lại giúp mình?", show_alert=True)
        return

    expense = await resolve_transaction_by_callback_id(db, user.id, args[0])
    if not expense:
        await answer_callback(callback_id, text="Giao dịch này mình không thấy nữa 🫣", show_alert=True)
        return

    if len(args) == 1:
        await edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=category_picker_keyboard(str(expense.id)),
        )
        await answer_callback(callback_id)
        return

    new_code = args[1]
    old_code = expense.category
    expense.category = new_code
    await db.flush()
    await db.refresh(expense)

    await _rerender_transaction_message(chat_id, message_id, expense)
    await answer_callback(callback_id, text="Đổi danh mục xong 👌")
    analytics.track(
        analytics.EventType.CATEGORY_CHANGED,
        user_id=user.id,
        properties={"from": old_code, "to": new_code},
    )


async def _handle_delete_transaction(
    *, db, user, args, callback_id, chat_id, message_id
):
    if not args:
        await answer_callback(callback_id, text="Hmm, thiếu thông tin giao dịch — thử tap lại giúp mình?", show_alert=True)
        return

    expense = await resolve_transaction_by_callback_id(db, user.id, args[0])
    if not expense:
        await answer_callback(callback_id, text="Giao dịch này mình không thấy nữa 🫣", show_alert=True)
        return

    await edit_message_reply_markup(
        chat_id=chat_id,
        message_id=message_id,
        reply_markup=confirm_delete_keyboard(str(expense.id)),
    )
    await answer_callback(callback_id)


async def _handle_confirm_action(
    *, db, user, args, callback_id, chat_id, message_id
):
    if len(args) < 2:
        await answer_callback(callback_id)
        return

    action, resource_id = args[0], args[1]
    if action != "delete":
        await answer_callback(callback_id)
        return

    expense = await resolve_transaction_by_callback_id(db, user.id, resource_id)
    if not expense:
        await answer_callback(callback_id, text="Giao dịch này mình không thấy nữa 🫣", show_alert=True)
        return

    await expense_service.delete_expense(db, user.id, expense.id)
    await edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text="🗑 Đã xóa giao dịch",
        parse_mode="HTML",
        reply_markup={"inline_keyboard": []},
    )
    await answer_callback(callback_id, text="Đã xóa ✅")
    analytics.track(
        analytics.EventType.TRANSACTION_DELETED,
        user_id=user.id,
        properties={"via": "confirm_dialog"},
    )


async def _handle_cancel_action(
    *, db, user, args, callback_id, chat_id, message_id
):
    """User tap 'Hủy'. Nếu có tx_id, đưa keyboard về trạng thái actions gốc."""
    if args:
        expense = await resolve_transaction_by_callback_id(db, user.id, args[0])
        if expense:
            await edit_message_reply_markup(
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=transaction_actions_keyboard(str(expense.id)),
            )
            await answer_callback(callback_id)
            return
    await edit_message_reply_markup(
        chat_id=chat_id, message_id=message_id, reply_markup={"inline_keyboard": []}
    )
    await answer_callback(callback_id)


async def _handle_undo_transaction(
    *, db, user, args, callback_id, chat_id, message_id
):
    """Undo chỉ trong UNDO_WINDOW_SECONDS đầu tiên sau khi tạo expense."""
    if not args:
        await answer_callback(callback_id, text="Hmm, thiếu thông tin giao dịch — thử tap lại giúp mình?", show_alert=True)
        return

    expense = await resolve_transaction_by_callback_id(db, user.id, args[0])
    if not expense:
        await answer_callback(callback_id, text="Giao dịch này mình không thấy nữa 🫣", show_alert=True)
        return

    created_at = expense.created_at
    if created_at and created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    age = (now - created_at).total_seconds() if created_at else 9999

    if age > UNDO_WINDOW_SECONDS:
        await answer_callback(
            callback_id,
            text="Quá muộn để hủy — dùng nút 🗑 Xóa nhé",
            show_alert=True,
        )
        return

    await expense_service.delete_expense(db, user.id, expense.id)
    await edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text="↶ Đã hủy giao dịch",
        parse_mode="HTML",
        reply_markup={"inline_keyboard": []},
    )
    await answer_callback(callback_id, text="Đã hủy ✅")
    analytics.track(
        analytics.EventType.TRANSACTION_DELETED,
        user_id=user.id,
        properties={"via": "undo", "age_seconds": round(age, 2)},
    )


async def _handle_edit_transaction(
    *, db, user, args, callback_id, chat_id, message_id
):
    """Placeholder — full amount/merchant edit UI ships in a later issue."""
    await answer_callback(
        callback_id,
        text="Sửa số tiền sẽ có trong bản cập nhật sắp tới — tạm thời dùng 'Đổi danh mục' hoặc 'Xóa' nhé",
        show_alert=True,
    )


__all__ = [
    "handle_transaction_callback",
    "UNDO_WINDOW_SECONDS",
]
