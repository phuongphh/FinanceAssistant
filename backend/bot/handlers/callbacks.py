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

from sqlalchemy.ext.asyncio import AsyncSession

from backend import analytics
from backend.bot.formatters.templates import format_transaction_confirmation
from backend.bot.handlers.transaction import (
    _normalize_category,
    resolve_transaction_by_callback_id,
    resolve_transactions_by_batch_id,
)
from backend.bot.handlers import photo_receipt
from backend.bot.keyboards.common import CallbackPrefix, parse_callback
from backend.bot.keyboards.transaction_keyboard import (
    category_picker_keyboard,
    confirm_delete_keyboard,
    e_wallet_provider_keyboard,
    transaction_actions_keyboard,
)
from backend.config.categories import get_all_categories
from backend.models.expense import Expense
from backend.schemas.expense import ExpenseCreate
from backend.services import expense_service
from backend.services.dashboard_service import get_user_by_telegram_id
from backend.services.telegram_service import (
    answer_callback,
    edit_message_reply_markup,
    edit_message_text,
    send_message,
)

logger = logging.getLogger(__name__)

UNDO_WINDOW_SECONDS = 5
_VALID_EXPENSE_CATEGORY_CODES = frozenset(cat.code for cat in get_all_categories())


async def _handle_source_selection_callback(
    db: AsyncSession, callback_query: dict[str, Any]
) -> bool:
    callback_id = callback_query["id"]
    data = callback_query.get("data", "")
    from_user = callback_query.get("from") or {}
    telegram_id = from_user.get("id")
    message = callback_query.get("message") or {}
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")
    user = await get_user_by_telegram_id(db, telegram_id) if telegram_id else None
    if not user:
        await answer_callback(
            callback_id, text="Bạn gửi /start trước nhé 🌱", show_alert=True
        )
        return True

    state = user.wizard_state or {}
    if state.get("flow") != "transaction_source_select":
        await answer_callback(
            callback_id, text="Yêu cầu này đã hết hạn rồi 🌱", show_alert=True
        )
        return True
    draft = dict(state.get("draft") or {})

    source_type = None
    wallet_provider = None
    if data == "txsrc:e_wallet":
        await edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=e_wallet_provider_keyboard(),
        )
        await answer_callback(callback_id)
        return True
    if data.startswith("txsrc_wallet:"):
        source_type = "e_wallet"
        wallet_provider = data.split(":", 1)[1]
    elif data.startswith("txsrc:"):
        chosen = data.split(":", 1)[1]
        if chosen != "skip":
            source_type = chosen

    expense_data = ExpenseCreate(
        amount=float(draft.get("amount", 0)),
        transaction_type=draft.get("transaction_type", "expense"),
        merchant=draft.get("merchant") or "Giao dịch",
        note=draft.get("note"),
        source="manual",
        source_type=source_type,
        e_wallet_provider=wallet_provider,
    )
    expense = await expense_service.create_expense(db, user.id, expense_data)
    from backend.services import wizard_service

    await wizard_service.clear(db, user.id)
    tx_sign = "+" if expense.transaction_type == "money_in" else "-"
    source_label = {
        "cash": "Tiền mặt",
        "bank_account": "Tài khoản",
        "momo": "Ví Momo",
        "vnpay": "Ví VNPay",
        "zalopay": "Ví ZaloPay",
        "viettelpay": "Ví ViettelPay",
    }.get(wallet_provider or source_type, "không liên kết nguồn")
    confirmation_text = (
        f"Đã ghi nhận {tx_sign}{float(expense.amount):,.0f}đ · {source_label}"
    )
    # Issue #799: ``editMessageText`` silently returns ``None`` when the
    # source-picker message is unreachable (deleted by the user, older
    # than Telegram's 48h edit window, etc.). Without a fallback the
    # user is stranded on the picker screen with no confirmation that
    # the transaction landed. Always send a fresh ``sendMessage`` when
    # the edit can't be confirmed so the user gets feedback either way.
    edit_result = None
    if chat_id is not None and message_id is not None:
        edit_result = await edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=confirmation_text,
            parse_mode=None,
            reply_markup={"inline_keyboard": []},
        )
    if edit_result is None and chat_id is not None:
        logger.warning(
            "txsrc confirmation edit returned None; sending fallback message "
            "(chat_id=%s message_id=%s)",
            chat_id,
            message_id,
        )
        await send_message(chat_id, confirmation_text, parse_mode=None)
    if expense.transaction_type == "expense" and (expense.raw_data or {}).get(
        "source_warning"
    ):
        await send_message(
            chat_id,
            "⚠️ Nguồn này có thể không đủ số dư, mình vẫn ghi nhận theo yêu cầu nhé.",
        )
    await answer_callback(callback_id, text="Đã ghi nhận ✅")
    return True


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

    if data.startswith("txsrc:") or data.startswith("txsrc_wallet:"):
        return await _handle_source_selection_callback(db, callback_query)
    if data == "expense:credit:add":
        from backend.bot.handlers.credit_card_entry import start_credit_card_create

        from_user = callback_query.get("from") or {}
        telegram_id = from_user.get("id")
        message = callback_query.get("message") or {}
        chat_id = message.get("chat", {}).get("id")
        user = await get_user_by_telegram_id(db, telegram_id) if telegram_id else None
        if not user or chat_id is None:
            return True
        await start_credit_card_create(db, chat_id, user)
        await answer_callback(callback_query["id"])
        return True

    prefix, args = parse_callback(data)

    handlers = {
        CallbackPrefix.CHANGE_CATEGORY: _handle_change_category,
        CallbackPrefix.DELETE_TRANSACTION: _handle_delete_transaction,
        CallbackPrefix.CONFIRM_ACTION: _handle_confirm_action,
        CallbackPrefix.CANCEL_ACTION: _handle_cancel_action,
        CallbackPrefix.UNDO_TRANSACTION: _handle_undo_transaction,
        CallbackPrefix.UNDO_TRANSACTION_BATCH: _handle_undo_transaction_batch,
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

    user = await get_user_by_telegram_id(db, telegram_id) if telegram_id else None

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


async def _handle_change_category(*, db, user, args, callback_id, chat_id, message_id):
    """2-step flow: show picker → update DB + re-render message."""
    if not args:
        await answer_callback(
            callback_id,
            text="Hmm, thiếu thông tin giao dịch — thử tap lại giúp mình?",
            show_alert=True,
        )
        return

    expense = await resolve_transaction_by_callback_id(db, user.id, args[0])
    if not expense:
        await answer_callback(
            callback_id, text="Giao dịch này mình không thấy nữa 🫣", show_alert=True
        )
        return

    if len(args) == 1:
        await edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=category_picker_keyboard(str(expense.id)),
        )
        await answer_callback(callback_id)
        return

    new_code = str(args[1]).strip().lower()
    if new_code not in _VALID_EXPENSE_CATEGORY_CODES:
        await answer_callback(
            callback_id,
            text="Danh mục không hợp lệ — bạn chọn lại trong danh sách nhé.",
            show_alert=True,
        )
        return
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
        await answer_callback(
            callback_id,
            text="Hmm, thiếu thông tin giao dịch — thử tap lại giúp mình?",
            show_alert=True,
        )
        return

    expense = await resolve_transaction_by_callback_id(db, user.id, args[0])
    if not expense:
        await answer_callback(
            callback_id, text="Giao dịch này mình không thấy nữa 🫣", show_alert=True
        )
        return

    await edit_message_reply_markup(
        chat_id=chat_id,
        message_id=message_id,
        reply_markup=confirm_delete_keyboard(str(expense.id)),
    )
    await answer_callback(callback_id)


async def _handle_confirm_action(*, db, user, args, callback_id, chat_id, message_id):
    if len(args) < 2:
        await answer_callback(callback_id)
        return

    action, resource_id = args[0], args[1]
    if action == "receipt":
        ok = await photo_receipt.confirm_pending_receipt(
            db=db, user=user, token=resource_id
        )
        if not ok:
            await answer_callback(
                callback_id, text="Phiên xác nhận đã hết hạn.", show_alert=True
            )
            return
        await edit_message_reply_markup(
            chat_id=chat_id, message_id=message_id, reply_markup={"inline_keyboard": []}
        )
        await answer_callback(callback_id, text="Đã lưu khoản chi ✅")
        return
    if action != "delete":
        await answer_callback(callback_id)
        return

    expense = await resolve_transaction_by_callback_id(db, user.id, resource_id)
    if not expense:
        await answer_callback(
            callback_id, text="Giao dịch này mình không thấy nữa 🫣", show_alert=True
        )
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


async def _handle_cancel_action(*, db, user, args, callback_id, chat_id, message_id):
    """User tap 'Hủy'. Nếu có tx_id, đưa keyboard về trạng thái actions gốc."""
    if len(args) >= 2 and args[0] == "receipt":
        await edit_message_reply_markup(
            chat_id=chat_id, message_id=message_id, reply_markup={"inline_keyboard": []}
        )
        await answer_callback(callback_id, text="Đã huỷ")
        return
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


async def _handle_undo_transaction(*, db, user, args, callback_id, chat_id, message_id):
    """Undo chỉ trong UNDO_WINDOW_SECONDS đầu tiên sau khi tạo expense."""
    if not args:
        await answer_callback(
            callback_id,
            text="Hmm, thiếu thông tin giao dịch — thử tap lại giúp mình?",
            show_alert=True,
        )
        return

    expense = await resolve_transaction_by_callback_id(db, user.id, args[0])
    if not expense:
        await answer_callback(
            callback_id, text="Giao dịch này mình không thấy nữa 🫣", show_alert=True
        )
        return

    created_at = expense.created_at
    if created_at and created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    age = (now - created_at).total_seconds() if created_at else 9999

    if age > UNDO_WINDOW_SECONDS:
        await answer_callback(
            callback_id,
            text="Hết hạn huỷ nhanh — mở Mini App rồi bấm ↩️ Huỷ giao dịch nhé",
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


async def _handle_undo_transaction_batch(
    *, db, user, args, callback_id, chat_id, message_id
):
    """Undo toàn bộ batch trong UNDO_WINDOW_SECONDS đầu tiên."""
    if not args:
        await answer_callback(
            callback_id,
            text="Hmm, thiếu thông tin giao dịch — thử tap lại giúp mình?",
            show_alert=True,
        )
        return

    expenses = await resolve_transactions_by_batch_id(db, user.id, args[0])
    if not expenses:
        await answer_callback(
            callback_id,
            text="Nhóm giao dịch này mình không thấy nữa 🫣",
            show_alert=True,
        )
        return

    now = datetime.now(timezone.utc)
    ages: list[float] = []
    for expense in expenses:
        created_at = expense.created_at
        if created_at and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        ages.append((now - created_at).total_seconds() if created_at else 9999)

    age = max(ages, default=9999)
    if age > UNDO_WINDOW_SECONDS:
        await answer_callback(
            callback_id,
            text="Hết hạn huỷ nhanh — mở Mini App rồi bấm ↩️ Huỷ giao dịch nhé",
            show_alert=True,
        )
        return

    for expense in expenses:
        await expense_service.delete_expense(db, user.id, expense.id)
    await edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=f"↶ Đã hủy {len(expenses)} giao dịch",
        parse_mode="HTML",
        reply_markup={"inline_keyboard": []},
    )
    await answer_callback(callback_id, text="Đã hủy tất cả ✅")
    analytics.track(
        analytics.EventType.TRANSACTION_DELETED,
        user_id=user.id,
        properties={
            "via": "undo_batch",
            "count": len(expenses),
            "age_seconds": round(age, 2),
        },
    )


async def _handle_edit_transaction(*, db, user, args, callback_id, chat_id, message_id):
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
