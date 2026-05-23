"""Recurring-pattern wizard + reminder action handlers.

Two callback prefixes share this module:
- ``recurring:*`` — pattern CRUD (S7) + auto-detection responses (S8)
- ``reminder:*`` — reminder action handlers (S10)

The wizard flow:

    recurring_add — name → amount → category → schedule_day
                    → reminders_toggle → save

State lives on ``users.wizard_state`` (same JSONB as asset / income
wizards). Step names use the ``recurring_`` prefix so the worker's
text-input dispatch can isolate them.

Reminder action flow (S10):

    reminder:paid → optional amount edit (default = expected_amount)
                    → record_occurrence
    reminder:delay → snooze 2 days
    reminder:disable → enable_reminders=False

Layer contract: handlers read/mutate DB through services, never
commit — worker owns the transaction boundary.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from backend import analytics
from backend.bot.formatters.money import format_money_short
from backend.bot.keyboards.common import parse_callback
from backend.bot.keyboards.recurring_keyboard import (
    CB_RECURRING,
    CB_REMINDER,
    recurring_category_keyboard,
    recurring_disable_confirm_keyboard,
    recurring_list_actions_keyboard,
    recurring_list_footer_keyboard,
    recurring_add_success_keyboard,
    recurring_manage_list_keyboard,
    recurring_reminders_toggle_keyboard,
)
from backend.config.categories import get_category
from backend.models.recurring_pattern import PatternSuggestionLog
from backend.models.user import User
from backend.services import recurring_service, wizard_service
from backend.services.dashboard_service import get_user_by_telegram_id
from backend.services.telegram_service import answer_callback, send_message
from backend.wealth.amount_parser import has_negative_sign, parse_amount

logger = logging.getLogger(__name__)


class RecurringEvent:
    WIZARD_OPENED = "recurring_wizard_opened"
    PATTERN_ADDED = "recurring_pattern_added"
    PATTERN_UPDATED = "recurring_pattern_updated"
    PATTERN_DISABLED = "recurring_pattern_disabled"
    REMINDER_PAID = "reminder_action_paid"
    REMINDER_DELAYED = "reminder_action_delayed"
    REMINDER_DISABLED = "reminder_action_disabled"
    REMINDER_ENABLED = "reminder_action_enabled"
    SUGGESTION_ACCEPTED = "suggestion_accepted"
    SUGGESTION_REJECTED = "suggestion_rejected"
    WIZARD_CANCELED = "recurring_wizard_canceled"
    PARSE_FAILED = "recurring_wizard_parse_failed"


FLOW_ADD = "recurring_add"
FLOW_EDIT = "recurring_edit"
FLOW_REMINDER_PAID = "reminder_paid_amount"


# ---------- List view --------------------------------------------------


def _format_pattern_line(pattern, index: int) -> str:
    cat = get_category(pattern.category)
    active_tag = "" if pattern.is_active else " · ⏸️ tạm dừng"
    bell = "🔔" if pattern.enable_reminders else "🔕"
    day_str = (
        f"ngày {pattern.expected_day_of_month}"
        if pattern.expected_day_of_month
        else "không cố định"
    )
    return (
        f"{index}. {cat.emoji} <b>{pattern.name}</b>{active_tag}\n"
        f"   {format_money_short(pattern.expected_amount)}/tháng · "
        f"{cat.name_vi} · 📅 {day_str} · {bell}"
    )


async def show_recurring_list(
    db: AsyncSession, chat_id: int, user: User
) -> None:
    """Render a compact, read-only recurring-pattern overview."""
    patterns = await recurring_service.get_active_patterns(
        db, user.id, include_inactive=True,
    )
    if not patterns:
        await send_message(
            chat_id=chat_id,
            text=(
                "🔄 <b>Khoản định kỳ</b>\n\n"
                "Chưa có khoản nào. Thêm khoản đầu tiên — "
                "thuê nhà, internet, gym, Netflix…"
            ),
            parse_mode="HTML",
            reply_markup=recurring_list_footer_keyboard(),
        )
        return

    total_monthly = sum(
        (Decimal(p.expected_amount) for p in patterns if p.is_active),
        Decimal(0),
    )
    lines = [
        "🔄 <b>Khoản định kỳ</b>",
        "",
        f"📊 Tổng/tháng: <b>{format_money_short(total_monthly)}</b>",
        "",
    ]
    lines.extend(_format_pattern_line(p, i) for i, p in enumerate(patterns, 1))
    await send_message(
        chat_id=chat_id,
        text="\n\n".join(lines),
        parse_mode="HTML",
        reply_markup=recurring_list_footer_keyboard(),
    )


async def show_recurring_manage_list(
    db: AsyncSession, chat_id: int, user: User
) -> None:
    """Render the picker for edit/reminder/delete actions."""
    patterns = await recurring_service.get_active_patterns(
        db, user.id, include_inactive=True,
    )
    if not patterns:
        await send_message(
            chat_id=chat_id,
            text="Chưa có khoản định kỳ nào để sửa nhé.",
            reply_markup=recurring_list_footer_keyboard(),
        )
        return
    await send_message(
        chat_id=chat_id,
        text=(
            "✏️ <b>Sửa khoản định kỳ</b>\n\n"
            "Chọn 1 khoản bên dưới để sửa số tiền, bật/tắt nhắc, hoặc xoá."
        ),
        parse_mode="HTML",
        reply_markup=recurring_manage_list_keyboard(patterns),
    )


async def show_recurring_pattern_actions(
    db: AsyncSession, chat_id: int, user: User, pattern_id_str: str
) -> None:
    try:
        pattern_id = uuid.UUID(pattern_id_str)
    except ValueError:
        await send_message(chat_id=chat_id, text="Không tìm thấy khoản.")
        return
    pattern = await recurring_service.get_pattern_by_id(db, user.id, pattern_id)
    if pattern is None:
        await send_message(chat_id=chat_id, text="Không tìm thấy khoản.")
        return

    await send_message(
        chat_id=chat_id,
        text=(
            "Bạn muốn làm gì với khoản này?\n\n"
            f"{_format_pattern_line(pattern, 1)}"
        ),
        parse_mode="HTML",
        reply_markup=recurring_list_actions_keyboard(
            pattern.id, enable_reminders=pattern.enable_reminders,
        ),
    )


# ---------- Add wizard -------------------------------------------------


async def start_recurring_wizard(
    db: AsyncSession, chat_id: int, user: User
) -> None:
    await wizard_service.start_flow(
        db, user.id, FLOW_ADD, step="name", draft={},
    )
    await send_message(
        chat_id=chat_id,
        text=(
            "🔄 <b>Thêm khoản định kỳ</b>\n\n"
            "💬 <b>Tên khoản này là gì?</b>\n\n"
            "Ví dụ: <code>Thuê nhà</code>, <code>Internet</code>, "
            "<code>Netflix</code>"
        ),
        parse_mode="HTML",
    )
    analytics.track(RecurringEvent.WIZARD_OPENED, user_id=user.id)


async def cancel_wizard(
    db: AsyncSession, chat_id: int, user: User
) -> bool:
    flow = (user.wizard_state or {}).get("flow") or ""
    if not flow.startswith("recurring_") and flow != FLOW_REMINDER_PAID:
        return False
    await wizard_service.clear(db, user.id)
    analytics.track(RecurringEvent.WIZARD_CANCELED, user_id=user.id)
    await send_message(
        chat_id=chat_id, text="Đã huỷ. Quay lại lúc nào cũng được 👋",
    )
    return True


async def _handle_name_input(
    db: AsyncSession, chat_id: int, user: User, text: str, draft: dict,
) -> None:
    name = text.strip()
    if not name:
        await send_message(chat_id=chat_id, text="Nhập tên giúp mình nhé 🙂")
        return
    if len(name) > 200:
        await send_message(chat_id=chat_id, text="Tên tối đa 200 ký tự.")
        return

    await wizard_service.update_step(
        db, user.id, step="amount", draft_patch={"name": name},
    )
    await send_message(
        chat_id=chat_id,
        text=(
            f"✅ <b>{name}</b>\n\n"
            "💰 <b>Số tiền hàng tháng?</b>\n\n"
            "Ví dụ: <code>15tr</code>, <code>500k</code>"
        ),
        parse_mode="HTML",
    )


async def _handle_amount_input(
    db: AsyncSession, chat_id: int, user: User, text: str, draft: dict,
) -> None:
    if has_negative_sign(text):
        await send_message(chat_id=chat_id, text="Số tiền phải > 0 nhé 🙂")
        return
    amount = parse_amount(text)
    if amount is None or amount <= 0:
        analytics.track(
            RecurringEvent.PARSE_FAILED, user_id=user.id,
            properties={"flow": FLOW_ADD, "field": "amount"},
        )
        await send_message(
            chat_id=chat_id,
            text="Mình chưa hiểu. Ví dụ: <code>15tr</code> hoặc <code>500k</code>",
            parse_mode="HTML",
        )
        return

    await wizard_service.update_step(
        db, user.id, step="category", draft_patch={"amount": float(amount)},
    )
    await send_message(
        chat_id=chat_id,
        text=(
            f"✅ {format_money_short(amount)}/tháng\n\n"
            "🏷️ <b>Loại nào?</b>"
        ),
        parse_mode="HTML",
        reply_markup=recurring_category_keyboard(),
    )


async def _handle_category_pick(
    db: AsyncSession, chat_id: int, user: User, code: str, draft: dict,
) -> None:
    cat = get_category(code)
    await wizard_service.update_step(
        db, user.id, step="schedule_day", draft_patch={"category": cat.code},
    )
    await send_message(
        chat_id=chat_id,
        text=(
            f"{cat.emoji} {cat.name_vi}\n\n"
            "📅 <b>Hàng tháng vào ngày nào?</b>\n\n"
            "Số từ 1-31. Gõ <code>0</code> nếu không cố định."
        ),
        parse_mode="HTML",
    )


async def _handle_schedule_day_input(
    db: AsyncSession, chat_id: int, user: User, text: str, draft: dict,
) -> None:
    cleaned = text.strip()
    if cleaned == "0":
        day = None
    else:
        if not cleaned.isdigit():
            await send_message(
                chat_id=chat_id,
                text="Nhập số từ 1-31, hoặc <code>0</code>.",
                parse_mode="HTML",
            )
            return
        day = int(cleaned)
        if not 1 <= day <= 31:
            await send_message(chat_id=chat_id, text="Ngày phải từ 1-31.")
            return

    await wizard_service.update_step(
        db, user.id, step="reminders", draft_patch={"schedule_day": day},
    )
    await send_message(
        chat_id=chat_id,
        text="🔔 <b>Bật nhắc nhở khi tới hạn?</b>",
        parse_mode="HTML",
        reply_markup=recurring_reminders_toggle_keyboard(),
    )


async def _handle_reminders_pick(
    db: AsyncSession, chat_id: int, user: User, choice: str, draft: dict,
) -> None:
    """Final step — save the pattern."""
    if choice not in ("on", "off"):
        await send_message(chat_id=chat_id, text="Lựa chọn không hợp lệ.")
        return
    enable = choice == "on"
    try:
        pattern = await recurring_service.add_pattern(
            db, user.id,
            name=draft.get("name", ""),
            category=draft.get("category", "other"),
            expected_amount=Decimal(str(draft.get("amount") or 0)),
            schedule_type="monthly",
            expected_day_of_month=draft.get("schedule_day"),
            enable_reminders=enable,
            user_confirmed=True,
        )
    except ValueError as exc:
        logger.warning("recurring add_pattern failed: %s", exc)
        await wizard_service.clear(db, user.id)
        await send_message(
            chat_id=chat_id,
            text="Có gì đó chưa đúng — bạn thử lại từ đầu nhé.",
        )
        return

    await wizard_service.clear(db, user.id)
    analytics.track(
        RecurringEvent.PATTERN_ADDED, user_id=user.id,
        properties={
            "category": pattern.category,
            "schedule_day": pattern.expected_day_of_month,
            "enable_reminders": pattern.enable_reminders,
        },
    )

    cat = get_category(pattern.category)
    bell_line = (
        f"   🔔 Sẽ nhắc {pattern.reminder_days_before} ngày trước hạn"
        if pattern.enable_reminders
        else "   🔕 Không nhắc"
    )
    day_line = (
        f"   📅 Ngày {pattern.expected_day_of_month} hàng tháng"
        if pattern.expected_day_of_month
        else "   📅 Không cố định"
    )
    await send_message(
        chat_id=chat_id,
        text=(
            f"✅ Đã thêm {cat.emoji} <b>{pattern.name}</b>\n"
            f"   {format_money_short(pattern.expected_amount)}/tháng · {cat.name_vi}\n"
            f"{day_line}\n"
            f"{bell_line}"
        ),
        parse_mode="HTML",
        reply_markup=recurring_add_success_keyboard(),
    )


# ---------- Edit (amount only) flow -----------------------------------


async def _handle_edit_pick(
    db: AsyncSession, chat_id: int, user: User, pattern_id_str: str,
) -> None:
    try:
        pattern_id = uuid.UUID(pattern_id_str)
    except ValueError:
        await send_message(chat_id=chat_id, text="Không tìm thấy khoản.")
        return
    pattern = await recurring_service.get_pattern_by_id(db, user.id, pattern_id)
    if pattern is None:
        await send_message(chat_id=chat_id, text="Không tìm thấy khoản.")
        return

    await wizard_service.start_flow(
        db, user.id, FLOW_EDIT, step="amount",
        draft={"pattern_id": str(pattern_id)},
    )
    await send_message(
        chat_id=chat_id,
        text=(
            f"✏️ Sửa <b>{pattern.name}</b>\n\n"
            f"Số tiền hiện tại: {format_money_short(pattern.expected_amount)}/tháng\n\n"
            "Nhập số tiền mới:"
        ),
        parse_mode="HTML",
    )


async def _handle_edit_amount_input(
    db: AsyncSession, chat_id: int, user: User, text: str, draft: dict,
) -> None:
    if has_negative_sign(text):
        await send_message(chat_id=chat_id, text="Số tiền phải > 0 nhé 🙂")
        return
    amount = parse_amount(text)
    if amount is None or amount <= 0:
        await send_message(
            chat_id=chat_id, text="Mình chưa hiểu. Ví dụ: <code>16tr</code>",
            parse_mode="HTML",
        )
        return
    try:
        pattern_id = uuid.UUID(str(draft.get("pattern_id")))
    except (TypeError, ValueError):
        await wizard_service.clear(db, user.id)
        await send_message(chat_id=chat_id, text="Có lỗi với wizard.")
        return

    await recurring_service.update_pattern(
        db, user.id, pattern_id, expected_amount=Decimal(amount),
    )
    await wizard_service.clear(db, user.id)
    analytics.track(
        RecurringEvent.PATTERN_UPDATED, user_id=user.id,
        properties={"field": "expected_amount"},
    )
    await send_message(
        chat_id=chat_id,
        text=f"✅ Đã cập nhật: <b>{format_money_short(amount)}</b>",
        parse_mode="HTML",
    )


# ---------- Disable (2-tap) ------------------------------------------


async def _handle_disable_show_confirm(
    db: AsyncSession, chat_id: int, user: User, pattern_id_str: str,
) -> None:
    try:
        uuid.UUID(pattern_id_str)
    except ValueError:
        await send_message(chat_id=chat_id, text="Không tìm thấy khoản.")
        return
    await send_message(
        chat_id=chat_id,
        text="🗑️ <b>Xoá khoản định kỳ này?</b>\nMình sẽ ngưng nhắc nhở.",
        parse_mode="HTML",
        reply_markup=recurring_disable_confirm_keyboard(pattern_id_str),
    )


async def _handle_reminder_enable(
    db: AsyncSession, chat_id: int, user: User, pattern_id_str: str,
) -> None:
    try:
        pattern_id = uuid.UUID(pattern_id_str)
    except ValueError:
        await send_message(chat_id=chat_id, text="Không tìm thấy khoản.")
        return
    try:
        await recurring_service.update_pattern(
            db, user.id, pattern_id, enable_reminders=True,
        )
    except ValueError:
        await send_message(chat_id=chat_id, text="Không tìm thấy khoản.")
        return
    analytics.track(RecurringEvent.REMINDER_ENABLED, user_id=user.id)
    await send_message(chat_id=chat_id, text="🔔 Đã bật nhắc nhở lại.")


async def _handle_disable_confirm(
    db: AsyncSession, chat_id: int, user: User, pattern_id_str: str,
) -> None:
    try:
        pattern_id = uuid.UUID(pattern_id_str)
    except ValueError:
        await send_message(chat_id=chat_id, text="Không tìm thấy khoản.")
        return
    try:
        await recurring_service.disable_pattern(db, user.id, pattern_id)
    except ValueError:
        await send_message(chat_id=chat_id, text="Không tìm thấy khoản.")
        return
    analytics.track(RecurringEvent.PATTERN_DISABLED, user_id=user.id)
    await send_message(chat_id=chat_id, text="🗑️ Đã xoá.")


# ---------- Reminder action handlers (S10) ---------------------------


async def _handle_reminder_paid(
    db: AsyncSession, chat_id: int, user: User, pattern_id_str: str,
) -> None:
    """User tapped "✅ Đã trả".

    Spec wants a wizard ("Số tiền đã trả?" + optional note) but the
    overwhelmingly-common case is "yes, the expected amount". So we
    record the occurrence at expected_amount immediately and let the
    user override only if needed (next message → enters amount-edit
    flow, currently unwired — out of scope for Epic 3 minimum).
    """
    try:
        pattern_id = uuid.UUID(pattern_id_str)
    except ValueError:
        await send_message(chat_id=chat_id, text="Không tìm thấy khoản.")
        return
    pattern = await recurring_service.get_pattern_by_id(db, user.id, pattern_id)
    if pattern is None:
        await send_message(chat_id=chat_id, text="Không tìm thấy khoản.")
        return

    expense = await recurring_service.record_occurrence(
        db, user.id, pattern_id, source="reminder_paid",
    )
    next_date = recurring_service.get_next_expected_date(pattern)
    analytics.track(
        RecurringEvent.REMINDER_PAID, user_id=user.id,
        properties={"pattern_id": str(pattern_id)},
    )
    await send_message(
        chat_id=chat_id,
        text=(
            f"✅ Đã ghi nhận {format_money_short(expense.amount)} cho "
            f"<b>{pattern.name}</b>.\n"
            f"📅 Lần sau dự kiến: <b>{next_date.strftime('%d/%m/%Y')}</b>"
        ),
        parse_mode="HTML",
    )


async def _handle_reminder_delay(
    db: AsyncSession, chat_id: int, user: User, pattern_id_str: str,
) -> None:
    try:
        pattern_id = uuid.UUID(pattern_id_str)
    except ValueError:
        await send_message(chat_id=chat_id, text="Không tìm thấy khoản.")
        return
    try:
        await recurring_service.snooze_pattern(db, user.id, pattern_id, days=2)
    except ValueError:
        await send_message(chat_id=chat_id, text="Không tìm thấy khoản.")
        return
    analytics.track(RecurringEvent.REMINDER_DELAYED, user_id=user.id)
    await send_message(
        chat_id=chat_id, text="⏭️ Hiểu rồi, mình nhắc lại sau 2 ngày.",
    )


async def _handle_reminder_disable(
    db: AsyncSession, chat_id: int, user: User, pattern_id_str: str,
) -> None:
    try:
        pattern_id = uuid.UUID(pattern_id_str)
    except ValueError:
        await send_message(chat_id=chat_id, text="Không tìm thấy khoản.")
        return
    try:
        await recurring_service.disable_reminders(db, user.id, pattern_id)
    except ValueError:
        await send_message(chat_id=chat_id, text="Không tìm thấy khoản.")
        return
    analytics.track(RecurringEvent.REMINDER_DISABLED, user_id=user.id)
    await send_message(
        chat_id=chat_id,
        text=(
            "🔕 OK, mình không nhắc nữa. Mở lại bất cứ lúc nào trong "
            "/menu → Chi tiêu → Khoản định kỳ."
        ),
    )


# ---------- Suggestion responses (S8) --------------------------------


async def _handle_suggestion_accept(
    db: AsyncSession, chat_id: int, user: User, suggestion_id_str: str,
) -> None:
    """User tapped "Đúng, ghi nhận" on an auto-detected suggestion.

    Promote the log row's payload into a real RecurringPattern, then
    stamp the log with outcome=accepted + the new pattern_id so the
    detector can de-spam future runs.
    """
    try:
        suggestion_id = int(suggestion_id_str)
    except ValueError:
        await send_message(chat_id=chat_id, text="Không tìm thấy gợi ý.")
        return
    log = await db.get(PatternSuggestionLog, suggestion_id)
    if log is None or log.user_id != user.id:
        await send_message(chat_id=chat_id, text="Không tìm thấy gợi ý.")
        return
    if log.outcome is not None:
        await send_message(
            chat_id=chat_id,
            text=f"Gợi ý này đã được xử lý ({log.outcome}).",
        )
        return

    cat = get_category(log.category)
    pattern = await recurring_service.add_pattern(
        db, user.id,
        name=f"{cat.name_vi} (auto-detected)",
        category=log.category,
        expected_amount=Decimal(log.suggested_amount),
        schedule_type="monthly",
        expected_day_of_month=log.typical_day,
        enable_reminders=True,
        auto_detected=True,
        user_confirmed=True,
    )
    log.outcome = "accepted"
    log.pattern_id = pattern.id
    log.resolved_at = datetime.utcnow()
    analytics.track(
        RecurringEvent.SUGGESTION_ACCEPTED, user_id=user.id,
        properties={"category": log.category},
    )
    await send_message(
        chat_id=chat_id,
        text=(
            f"✅ Đã ghi nhận {cat.emoji} <b>{pattern.name}</b>.\n"
            f"   {format_money_short(pattern.expected_amount)}/tháng · "
            f"ngày {pattern.expected_day_of_month or '?'}"
        ),
        parse_mode="HTML",
    )


async def _handle_suggestion_reject(
    db: AsyncSession, chat_id: int, user: User, suggestion_id_str: str,
) -> None:
    try:
        suggestion_id = int(suggestion_id_str)
    except ValueError:
        await send_message(chat_id=chat_id, text="Không tìm thấy gợi ý.")
        return
    log = await db.get(PatternSuggestionLog, suggestion_id)
    if log is None or log.user_id != user.id:
        await send_message(chat_id=chat_id, text="Không tìm thấy gợi ý.")
        return
    log.outcome = "rejected"
    log.resolved_at = datetime.utcnow()
    analytics.track(
        RecurringEvent.SUGGESTION_REJECTED, user_id=user.id,
        properties={"category": log.category},
    )
    await send_message(
        chat_id=chat_id,
        text="OK, bỏ qua nhé. Mình sẽ không gợi ý lại khoản này.",
    )


# ---------- Public dispatch ------------------------------------------


_TEXT_DISPATCH = {
    (FLOW_ADD, "name"): _handle_name_input,
    (FLOW_ADD, "amount"): _handle_amount_input,
    (FLOW_ADD, "schedule_day"): _handle_schedule_day_input,
    (FLOW_EDIT, "amount"): _handle_edit_amount_input,
}


async def handle_recurring_text_input(
    db: AsyncSession, message: dict,
) -> bool:
    """Consume free text if the user is mid-recurring-wizard.

    Returns True for any ``recurring_*`` flow — at button-step
    states (category, reminders) we send a "tap a button" nudge so
    stray text doesn't leak into the NL parser. Same defensive
    pattern as the asset / income wizards.
    """
    text = (message.get("text") or "").strip()
    if not text or text.startswith("/"):
        return False
    chat_id = message["chat"]["id"]
    telegram_id = (message.get("from") or {}).get("id")
    if telegram_id is None:
        return False
    user = await get_user_by_telegram_id(db, telegram_id)
    if user is None or not user.wizard_state:
        return False
    flow = wizard_service.get_flow(user.wizard_state)
    step = wizard_service.get_step(user.wizard_state)
    if not (flow or "").startswith("recurring_"):
        return False

    handler = _TEXT_DISPATCH.get((flow, step))
    if handler is None:
        analytics.track(
            RecurringEvent.PARSE_FAILED, user_id=user.id,
            properties={"flow": flow, "step": step,
                        "reason": "text_at_button_step"},
        )
        await send_message(
            chat_id=chat_id,
            text=(
                "👆 Bạn đang trong wizard <b>khoản định kỳ</b> — "
                "tap nút phía trên (hoặc /huy để thoát)."
            ),
            parse_mode="HTML",
        )
        return True

    draft = wizard_service.get_draft(user.wizard_state)
    try:
        await handler(db, chat_id, user, text, draft)
    except Exception:
        logger.exception(
            "recurring wizard text handler crashed: flow=%s step=%s",
            flow, step,
        )
        await wizard_service.clear(db, user.id)
        await send_message(
            chat_id=chat_id, text="Có lỗi xảy ra, mình huỷ wizard.",
        )
    return True


async def _dispatch_recurring(
    db: AsyncSession, chat_id: int, user: User,
    action: str, arg: str | None,
) -> None:
    if action == "start":
        await start_recurring_wizard(db, chat_id, user)
        return
    if action == "list":
        await show_recurring_list(db, chat_id, user)
        return
    if action == "manage":
        await show_recurring_manage_list(db, chat_id, user)
        return
    if action == "select" and arg:
        await show_recurring_pattern_actions(db, chat_id, user, arg)
        return
    if action == "cancel":
        await wizard_service.clear(db, user.id)
        analytics.track(RecurringEvent.WIZARD_CANCELED, user_id=user.id)
        await send_message(chat_id=chat_id, text="Đã huỷ. 👋")
        return

    draft = wizard_service.get_draft(user.wizard_state)
    if action == "category" and arg:
        await _handle_category_pick(db, chat_id, user, arg, draft)
        return
    if action == "reminders" and arg:
        await _handle_reminders_pick(db, chat_id, user, arg, draft)
        return
    if action == "edit" and arg:
        await _handle_edit_pick(db, chat_id, user, arg)
        return
    if action == "reminder_on" and arg:
        await _handle_reminder_enable(db, chat_id, user, arg)
        return
    if action == "disable" and arg:
        await _handle_disable_show_confirm(db, chat_id, user, arg)
        return
    if action == "disable_confirm" and arg:
        await _handle_disable_confirm(db, chat_id, user, arg)
        return
    if action == "accept" and arg:
        await _handle_suggestion_accept(db, chat_id, user, arg)
        return
    if action == "reject" and arg:
        await _handle_suggestion_reject(db, chat_id, user, arg)
        return


async def _dispatch_reminder(
    db: AsyncSession, chat_id: int, user: User,
    action: str, arg: str | None,
) -> None:
    if action == "paid" and arg:
        await _handle_reminder_paid(db, chat_id, user, arg)
        return
    if action == "delay" and arg:
        await _handle_reminder_delay(db, chat_id, user, arg)
        return
    if action == "disable" and arg:
        await _handle_reminder_disable(db, chat_id, user, arg)
        return


async def handle_recurring_callback(
    db: AsyncSession, callback_query: dict,
) -> bool:
    """Route ``recurring:*`` and ``reminder:*`` callbacks. Returns
    True iff handled."""
    data: str = callback_query.get("data") or ""
    is_recurring = data.startswith(f"{CB_RECURRING}:") or data == CB_RECURRING
    is_reminder = data.startswith(f"{CB_REMINDER}:") or data == CB_REMINDER
    if not (is_recurring or is_reminder):
        return False

    callback_id = callback_query["id"]
    message = callback_query.get("message") or {}
    chat_id = (message.get("chat") or {}).get("id")
    telegram_id = (callback_query.get("from") or {}).get("id")
    if chat_id is None or telegram_id is None:
        await answer_callback(callback_id)
        return True

    user = await get_user_by_telegram_id(db, telegram_id)
    if user is None:
        await answer_callback(callback_id, text="Bạn cần /start trước nhé.")
        return True

    _, parts = parse_callback(data)
    action = parts[0] if parts else ""
    arg = parts[1] if len(parts) > 1 else None

    dispatcher = _dispatch_recurring if is_recurring else _dispatch_reminder
    await asyncio.gather(
        answer_callback(callback_id),
        dispatcher(db, chat_id, user, action, arg),
    )
    return True
