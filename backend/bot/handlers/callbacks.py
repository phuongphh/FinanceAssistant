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
from zoneinfo import ZoneInfo

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
    credit_card_source_keyboard,
    e_wallet_provider_keyboard,
    source_asset_keyboard,
    source_picker_keyboard,
    transaction_actions_keyboard,
    transaction_actions_with_done_keyboard,
    transaction_source_keyboard,
)
from backend.config.categories import get_all_categories
from backend.models.expense import Expense
from backend.schemas.expense import ExpenseCreate, ExpenseUpdate
from backend.services import expense_service, wizard_service
from backend.services.credit_card_service import list_credit_cards
from backend.services.expense_source_resolver import resolve_source_label_for_expense
from backend.services.portfolio_service import list_assets
from backend.services.dashboard_service import get_user_by_telegram_id
from backend.services.telegram_service import (
    answer_callback,
    edit_message_reply_markup,
    edit_message_text,
    send_message,
)

_VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

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
    if data == "txsrc:bank_pick":
        assets = await list_assets(db, user.id, asset_type="cash", limit=500, offset=0)
        bank_assets = [a for a in assets if (a.subtype or "").lower() in ("bank_checking", "bank_account")]
        if not bank_assets:
            await answer_callback(callback_id, text="Bạn chưa có tài khoản thanh toán nào 🌱", show_alert=True)
            return True
        await edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=source_asset_keyboard(bank_assets))
        await answer_callback(callback_id)
        return True
    if data == "txsrc:e_wallet":
        await edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=e_wallet_provider_keyboard(),
        )
        await answer_callback(callback_id)
        return True
    if data == "txsrc:back":
        await edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=transaction_source_keyboard(draft.get("transaction_type", "expense")),
        )
        await answer_callback(callback_id)
        return True
    if data == "txsrc:credit_card":
        cards = await list_credit_cards(db, user.id)
        if not cards:
            await answer_callback(callback_id, text="Bạn chưa có thẻ tín dụng nào 🌱", show_alert=True)
            return True
        await edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=credit_card_source_keyboard(cards),
        )
        await answer_callback(callback_id)
        return True
    source_credit_card_id = None
    source_asset_id = None
    selected_card_bank_name = None
    if data.startswith("txsrc_wallet:"):
        source_type = "e_wallet"
        wallet_provider = data.split(":", 1)[1]
    elif data.startswith("txsrc_card:"):
        source_type = "credit_card"
        requested_card_id = data.split(":", 1)[1]
        cards = await list_credit_cards(db, user.id)
        selected_card = next(
            (c for c in cards if str(c.id) == str(requested_card_id)),
            None,
        )
        if selected_card is None:
            await answer_callback(
                callback_id,
                text="Thẻ không hợp lệ hoặc đã bị xoá 🌱",
                show_alert=True,
            )
            return True
        source_credit_card_id = selected_card.id
        selected_card_bank_name = selected_card.bank_name
    elif data.startswith("txsrc_bank:"):
        source_type = "bank_account"
        source_asset_id = data.split(":", 1)[1]
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
        source_credit_card_id=source_credit_card_id,
        source_asset_id=source_asset_id,
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
        "credit_card": (
            f"Thẻ tín dụng {selected_card_bank_name}"
            if selected_card_bank_name
            else "Thẻ tín dụng"
        ),
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


def _to_vn_time(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_VN_TZ)


async def _rerender_transaction_message(
    chat_id: int,
    message_id: int,
    expense: Expense,
    *,
    edited: bool = False,
    db: AsyncSession | None = None,
) -> None:
    is_expense = expense.transaction_type == "expense"
    source_label = None
    if is_expense and db is not None:
        try:
            source_label = await resolve_source_label_for_expense(db, expense)
        except Exception:
            logger.exception("resolve_source_label_for_expense failed")
            source_label = None
    text = format_transaction_confirmation(
        merchant=expense.merchant or expense.note or "Giao dịch",
        amount=float(expense.amount),
        category_code=_normalize_category(expense.category),
        time=_to_vn_time(expense.created_at),
        source_label=source_label,
        show_edit_hint=is_expense,
    )
    reply_markup = (
        transaction_actions_with_done_keyboard(str(expense.id))
        if edited
        else transaction_actions_keyboard(str(expense.id))
    )
    await edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=text,
        parse_mode="HTML",
        reply_markup=reply_markup,
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

    if (
        data.startswith("txsrc:")
        or data.startswith("txsrc_wallet:")
        or data.startswith("txsrc_card:")
        or data.startswith("txsrc_bank:")
    ):
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
    if data.startswith("expense:credit:undo:"):
        from backend.bot.handlers.credit_card_entry import undo_credit_card_create

        from_user = callback_query.get("from") or {}
        telegram_id = from_user.get("id")
        message = callback_query.get("message") or {}
        chat_id = message.get("chat", {}).get("id")
        user = await get_user_by_telegram_id(db, telegram_id) if telegram_id else None
        if not user or chat_id is None:
            return True
        await undo_credit_card_create(db, chat_id, user, data.split(":")[-1])
        await answer_callback(callback_query["id"])
        return True

    if (
        data.startswith("chsrc_bk:")
        or data.startswith("chsrc_wl:")
        or data.startswith("chsrc_cc:")
    ):
        return await _handle_change_source_subpicker(db, callback_query)

    prefix, args = parse_callback(data)

    handlers = {
        CallbackPrefix.CHANGE_CATEGORY: _handle_change_category,
        CallbackPrefix.CHANGE_SOURCE: _handle_change_source,
        CallbackPrefix.EDIT_AMOUNT: _handle_edit_amount,
        CallbackPrefix.CONFIRM_EDIT_DONE: _handle_done_edit,
        CallbackPrefix.DELETE_TRANSACTION: _handle_delete_transaction,
        CallbackPrefix.CONFIRM_ACTION: _handle_confirm_action,
        CallbackPrefix.CANCEL_ACTION: _handle_cancel_action,
        CallbackPrefix.UNDO_TRANSACTION: _handle_undo_transaction,
        CallbackPrefix.UNDO_TRANSACTION_BATCH: _handle_undo_transaction_batch,
        CallbackPrefix.EDIT_TRANSACTION: _handle_edit_transaction,
        CallbackPrefix.RECEIPT_CATEGORY: _handle_receipt_category,
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

    await _rerender_transaction_message(
        chat_id, message_id, expense, edited=True, db=db
    )
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


async def _handle_receipt_category(
    *, db, user, args, callback_id, chat_id, message_id
):
    """User picked a category on a pending OCR receipt (before confirming).

    Updates the in-memory pending payload and re-renders the confirmation
    message in place so the chosen category is ticked and reflected in the
    body. The expense itself is only written on the later ``confirm`` tap.
    """
    if len(args) < 2:
        await answer_callback(callback_id)
        return

    token, code = args[0], str(args[1]).strip().lower()
    rendered = photo_receipt.set_pending_receipt_category(
        token=token, user=user, category=code
    )
    if rendered is None:
        await answer_callback(
            callback_id,
            text="Phiên xác nhận đã hết hạn — bạn chụp lại hoá đơn giúp mình nhé.",
            show_alert=True,
        )
        return

    text, keyboard = rendered
    await edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=text,
        parse_mode=None,
        reply_markup=keyboard,
    )
    await answer_callback(callback_id, text="Đã chọn danh mục 👌")


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


# --------- Issue #897: change source / edit amount / done-edit ---------


_SOURCE_TYPE_BY_SHORT = {
    "cash": "cash",
    "bank": "bank_account",
    "wallet": "e_wallet",
    "card": "credit_card",
}


async def _handle_change_source(*, db, user, args, callback_id, chat_id, message_id):
    """2-step source edit (mirror change_category).

    args[0] = expense_id (always)
    args[1] (optional) = "cash" | "bank" | "wallet" | "card"
        - "cash" applies immediately.
        - others swap the keyboard to the relevant sub-picker.
    """
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
        await wizard_service.start_flow(
            db,
            user.id,
            flow="transaction_source_edit",
            step="pick_kind",
            draft={
                "expense_id": str(expense.id),
                "chat_id": chat_id,
                "message_id": message_id,
            },
        )
        await edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=source_picker_keyboard(str(expense.id)),
        )
        await answer_callback(callback_id)
        return

    kind = str(args[1]).strip().lower()
    if kind == "cash":
        updated = await expense_service.update_expense(
            db,
            user.id,
            expense.id,
            ExpenseUpdate(
                source_type="cash",
                source_asset_id=None,
                source_credit_card_id=None,
                e_wallet_provider=None,
            ),
        )
        await wizard_service.clear(db, user.id)
        if updated is None:
            await answer_callback(
                callback_id, text="Không cập nhật được — thử lại nhé.", show_alert=True
            )
            return
        await _rerender_transaction_message(
            chat_id, message_id, updated, edited=True, db=db
        )
        await answer_callback(callback_id, text="Đổi nguồn tiền xong 👌")
        return

    if kind == "bank":
        assets = await list_assets(db, user.id, asset_type="cash", limit=500, offset=0)
        bank_assets = [
            a for a in assets if (a.subtype or "").lower() in ("bank_checking", "bank_account")
        ]
        if not bank_assets:
            await answer_callback(
                callback_id,
                text="Bạn chưa có tài khoản thanh toán nào 🌱",
                show_alert=True,
            )
            return
        rows: list[list[dict]] = [
            [
                {
                    "text": f"🏦 Thẻ thanh toán - {a.name}",
                    "callback_data": f"chsrc_bk:{a.id}",
                }
            ]
            for a in bank_assets
        ]
        rows.append(
            [
                {
                    "text": "↩️ Quay lại",
                    "callback_data": f"{CallbackPrefix.CHANGE_SOURCE}:{expense.id}",
                }
            ]
        )
        await edit_message_reply_markup(
            chat_id=chat_id, message_id=message_id, reply_markup={"inline_keyboard": rows}
        )
        await answer_callback(callback_id)
        return

    if kind == "wallet":
        rows = [
            [
                {"text": "Momo", "callback_data": "chsrc_wl:momo"},
                {"text": "VNPay", "callback_data": "chsrc_wl:vnpay"},
            ],
            [
                {"text": "ZaloPay", "callback_data": "chsrc_wl:zalopay"},
                {"text": "ViettelPay", "callback_data": "chsrc_wl:viettelpay"},
            ],
            [
                {
                    "text": "↩️ Quay lại",
                    "callback_data": f"{CallbackPrefix.CHANGE_SOURCE}:{expense.id}",
                }
            ],
        ]
        await edit_message_reply_markup(
            chat_id=chat_id, message_id=message_id, reply_markup={"inline_keyboard": rows}
        )
        await answer_callback(callback_id)
        return

    if kind == "card":
        cards = await list_credit_cards(db, user.id)
        if not cards:
            await answer_callback(
                callback_id,
                text="Bạn chưa có thẻ tín dụng nào 🌱",
                show_alert=True,
            )
            return
        rows = [
            [
                {
                    "text": f"💳 {c.bank_name}",
                    "callback_data": f"chsrc_cc:{c.id}",
                }
            ]
            for c in cards
        ]
        rows.append(
            [
                {
                    "text": "↩️ Quay lại",
                    "callback_data": f"{CallbackPrefix.CHANGE_SOURCE}:{expense.id}",
                }
            ]
        )
        await edit_message_reply_markup(
            chat_id=chat_id, message_id=message_id, reply_markup={"inline_keyboard": rows}
        )
        await answer_callback(callback_id)
        return

    await answer_callback(callback_id)


async def _handle_change_source_subpicker(
    db: AsyncSession, callback_query: dict[str, Any]
) -> bool:
    """Apply a source pick coming from a sub-picker (bank/wallet/card)."""
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
    if state.get("flow") != "transaction_source_edit":
        await answer_callback(
            callback_id, text="Yêu cầu này đã hết hạn rồi 🌱", show_alert=True
        )
        return True
    draft = dict(state.get("draft") or {})
    expense_id_str = draft.get("expense_id")
    if not expense_id_str:
        await answer_callback(callback_id, text="Yêu cầu này đã hết hạn rồi 🌱", show_alert=True)
        return True

    expense = await resolve_transaction_by_callback_id(db, user.id, expense_id_str)
    if not expense:
        await wizard_service.clear(db, user.id)
        await answer_callback(
            callback_id, text="Giao dịch này mình không thấy nữa 🫣", show_alert=True
        )
        return True

    update: ExpenseUpdate
    if data.startswith("chsrc_bk:"):
        asset_id = data.split(":", 1)[1]
        update = ExpenseUpdate(
            source_type="bank_account",
            source_asset_id=asset_id,
            source_credit_card_id=None,
            e_wallet_provider=None,
        )
    elif data.startswith("chsrc_wl:"):
        provider = data.split(":", 1)[1]
        update = ExpenseUpdate(
            source_type="e_wallet",
            e_wallet_provider=provider,
            source_asset_id=None,
            source_credit_card_id=None,
        )
    elif data.startswith("chsrc_cc:"):
        card_id = data.split(":", 1)[1]
        update = ExpenseUpdate(
            source_type="credit_card",
            source_credit_card_id=card_id,
            source_asset_id=None,
            e_wallet_provider=None,
        )
    else:
        await answer_callback(callback_id)
        return True

    updated = await expense_service.update_expense(db, user.id, expense.id, update)
    await wizard_service.clear(db, user.id)
    if updated is None:
        await answer_callback(
            callback_id, text="Không cập nhật được — thử lại nhé.", show_alert=True
        )
        return True
    await _rerender_transaction_message(
        chat_id, message_id, updated, edited=True, db=db
    )
    await answer_callback(callback_id, text="Đổi nguồn tiền xong 👌")
    return True


async def _handle_edit_amount(*, db, user, args, callback_id, chat_id, message_id):
    """Prompt user via force_reply, set wizard to capture next text message."""
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

    await wizard_service.start_flow(
        db,
        user.id,
        flow="transaction_amount_edit",
        step="await_amount",
        draft={
            "expense_id": str(expense.id),
            "chat_id": chat_id,
            "message_id": message_id,
        },
    )
    await send_message(
        chat_id=chat_id,
        text="Số tiền mới là bao nhiêu? (ví dụ: 45k, 1.2tr)",
        parse_mode=None,
        reply_markup={"force_reply": True, "selective": True},
    )
    await answer_callback(callback_id)


async def _handle_done_edit(*, db, user, args, callback_id, chat_id, message_id):
    """User taps ✅ Đồng ý — strip the keyboard, keep the message text."""
    await edit_message_reply_markup(
        chat_id=chat_id, message_id=message_id, reply_markup={"inline_keyboard": []}
    )
    await answer_callback(callback_id, text="Đã lưu ✅")


__all__ = [
    "handle_transaction_callback",
    "UNDO_WINDOW_SECONDS",
]
