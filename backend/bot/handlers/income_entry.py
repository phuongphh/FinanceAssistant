"""Income-stream wizard handler.

Mirrors the asset-entry wizard's structure (text dispatch table +
callback dispatcher) but runs a different flow:

    income_add — type → amount → schedule
                 → schedule_day (if monthly) | schedule_month (if annually)
                 → start_date pick → optional start_date_input
                 → save

Plus a list/edit/delete surface accessed via the menu's
``menu:cashflow:income`` action and ``income:list`` callback.

Layer contract: handler reads/mutates DB through services, never
commits — worker owns the transaction boundary.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from backend import analytics
from backend.bot.formatters.money import format_money_short
from backend.bot.keyboards.common import parse_callback
from backend.bot.keyboards.income_keyboard import (
    CB_INCOME,
    income_delete_confirm_keyboard,
    income_list_actions_keyboard,
    income_list_footer_keyboard,
    income_month_keyboard,
    income_schedule_keyboard,
    income_start_date_keyboard,
    income_type_picker_keyboard,
)
from backend.models.user import User
from backend.services import wizard_service
from backend.services.dashboard_service import get_user_by_telegram_id
from backend.services.telegram_service import answer_callback, send_message
from backend.wealth.amount_parser import has_negative_sign, parse_amount
from backend.wealth.income_types import (
    ScheduleType,
    StreamType,
    get_icon,
    get_label,
    is_passive_default,
    typical_schedule,
)
from backend.wealth.schemas.income import IncomeStreamCreate, IncomeStreamUpdate
from backend.wealth.services import income_service

logger = logging.getLogger(__name__)


class IncomeEvent:
    """Analytics events for the income-stream wizard."""
    WIZARD_OPENED = "income_wizard_opened"
    TYPE_PICKED = "income_wizard_type_picked"
    STREAM_ADDED = "income_stream_added"
    STREAM_UPDATED = "income_stream_updated"
    STREAM_DELETED = "income_stream_deleted"
    STREAM_PAUSED = "income_stream_paused"
    STREAM_RESUMED = "income_stream_resumed"
    WIZARD_CANCELED = "income_wizard_canceled"
    PARSE_FAILED = "income_wizard_parse_failed"


# Flow names persisted in wizard_state. ``income_*`` prefix so the
# text dispatcher can detect "user is mid income wizard" with a
# single startswith check (matches asset-entry's prefix pattern).
FLOW_ADD = "income_add"
FLOW_EDIT = "income_edit"


# ---------- Entry point + helpers ------------------------------------


async def show_income_list(
    db: AsyncSession, chat_id: int, user: User
) -> None:
    """Render the menu:cashflow:income list view.

    Empty state explains how to get started; populated state shows
    each stream with monthly equivalent + edit/pause/delete buttons.
    Aggregate footer shows total monthly + active/passive split so
    the headline number is visible without scrolling through rows.
    """
    streams = await income_service.get_active_streams(
        db, user.id, include_inactive=True,
    )
    if not streams:
        await send_message(
            chat_id=chat_id,
            text=(
                "💼 <b>Thu nhập của bạn</b>\n\n"
                "Chưa có nguồn thu nào. Thêm cái đầu tiên — "
                "lương / freelance / cổ tức / lãi tiết kiệm…"
            ),
            parse_mode="HTML",
            reply_markup=income_list_footer_keyboard(),
        )
        return

    breakdown = await income_service.get_income_breakdown(db, user.id)
    lines = [
        "💼 <b>Thu nhập của bạn</b>",
        "",
        f"📊 Tổng/tháng: <b>{format_money_short(breakdown.total_monthly)}</b>",
    ]
    if breakdown.passive_ratio is not None:
        lines.append(
            f"  • Chủ động: {format_money_short(breakdown.active_income)}\n"
            f"  • Thụ động: {format_money_short(breakdown.passive_income)}"
            f" ({breakdown.passive_ratio:.0f}%)"
        )
    lines.append("")
    await send_message(
        chat_id=chat_id, text="\n".join(lines), parse_mode="HTML",
    )

    # Each stream as its own message so the action keyboard sticks
    # right next to the row it modifies. Telegram doesn't let one
    # message mix multiple keyboard groups cleanly.
    for s in streams:
        icon = get_icon(s.stream_type)
        type_label = get_label(s.stream_type)
        active_marker = "" if s.is_active else " (⏸️ tạm dừng)"
        sched_label = _schedule_label(s.schedule_type)
        passive_tag = "thụ động" if s.is_passive else "chủ động"
        text = (
            f"{icon} <b>{s.name}</b>{active_marker}\n"
            f"   {type_label} · {passive_tag}\n"
            f"   {format_money_short(s.amount)}/{sched_label} "
            f"≈ {format_money_short(s.monthly_equivalent)}/tháng"
        )
        await send_message(
            chat_id=chat_id, text=text, parse_mode="HTML",
            reply_markup=income_list_actions_keyboard(
                s.id, is_active=s.is_active,
            ),
        )

    await send_message(
        chat_id=chat_id, text="—",
        reply_markup=income_list_footer_keyboard(),
    )


def _schedule_label(schedule_type: str) -> str:
    return {
        "monthly": "tháng",
        "quarterly": "quý",
        "annually": "năm",
        "ad_hoc": "lần",
    }.get(schedule_type, schedule_type)


async def start_income_wizard(
    db: AsyncSession, chat_id: int, user: User
) -> None:
    """Step 1 of the add flow: pick a type."""
    await wizard_service.start_flow(
        db, user.id, FLOW_ADD, step="type", draft={},
    )
    await send_message(
        chat_id=chat_id,
        text="💼 <b>Loại thu nhập?</b>",
        parse_mode="HTML",
        reply_markup=income_type_picker_keyboard(),
    )
    analytics.track(IncomeEvent.WIZARD_OPENED, user_id=user.id)


async def cancel_wizard(
    db: AsyncSession, chat_id: int, user: User
) -> bool:
    """Used by /huy + /cancel commands; returns True iff something
    was actually cancelled."""
    flow = (user.wizard_state or {}).get("flow") or ""
    if not flow.startswith("income_"):
        return False
    await wizard_service.clear(db, user.id)
    analytics.track(IncomeEvent.WIZARD_CANCELED, user_id=user.id)
    await send_message(
        chat_id=chat_id, text="Đã huỷ. Quay lại lúc nào cũng được 👋",
    )
    return True


# ---------- Add flow steps (callbacks + text inputs) ------------------


async def _handle_type_pick(
    db: AsyncSession, chat_id: int, user: User, stream_type: str,
) -> None:
    """Step 2: ask for amount. Pre-fill schedule with the YAML
    typical_schedule so step 3 can short-circuit to "use the default?"
    in a future polish — for now we still ask."""
    if stream_type not in {t.value for t in StreamType}:
        await send_message(chat_id=chat_id, text="Loại không hợp lệ.")
        return

    analytics.track(
        IncomeEvent.TYPE_PICKED, user_id=user.id,
        properties={"stream_type": stream_type},
    )
    await wizard_service.update_step(
        db, user.id, step="amount",
        draft_patch={
            "stream_type": stream_type,
            "is_passive": is_passive_default(stream_type),
            "typical_schedule": typical_schedule(stream_type),
        },
    )
    icon = get_icon(stream_type)
    label = get_label(stream_type)
    await send_message(
        chat_id=chat_id,
        text=(
            f"{icon} <b>{label}</b>\n\n"
            "💰 <b>Đặt tên + số tiền:</b>\n\n"
            "Ví dụ:\n"
            "• <code>Lương Tech 30tr</code>\n"
            "• <code>Cổ tức VNM 10tr</code>\n"
            "• <code>Lãi VCB 5tr</code>"
        ),
        parse_mode="HTML",
    )


async def _handle_amount_input(
    db: AsyncSession, chat_id: int, user: User, text: str, draft: dict,
) -> None:
    """Step 2 follow-up: parse "<name> <amount>" pair (mirrors cash
    flow's parse_label_and_amount). The name is mandatory — different
    from cash where we fall back to a generic "Tài khoản" label,
    because income streams have richer per-row context the user
    needs to identify in the list view."""
    if has_negative_sign(text):
        await send_message(
            chat_id=chat_id, text="Số tiền phải lớn hơn 0 nhé 🙂",
        )
        return

    parsed = _parse_name_and_amount(text)
    if parsed is None:
        analytics.track(IncomeEvent.PARSE_FAILED, user_id=user.id,
                        properties={"flow": FLOW_ADD, "field": "amount"})
        await send_message(
            chat_id=chat_id,
            text=(
                "Mình chưa hiểu 😅\n"
                "Format: <b>Tên + số tiền</b>\n"
                "Ví dụ: <code>Lương Tech 30tr</code>"
            ),
            parse_mode="HTML",
        )
        return

    name, amount = parsed
    if amount <= 0:
        await send_message(
            chat_id=chat_id, text="Số tiền phải lớn hơn 0 nhé 🙂",
        )
        return

    await wizard_service.update_step(
        db, user.id, step="schedule",
        draft_patch={"name": name, "amount": float(amount)},
    )
    await send_message(
        chat_id=chat_id,
        text=(
            f"✅ <b>{name}</b> — {format_money_short(amount)}\n\n"
            "📅 <b>Bao lâu nhận 1 lần?</b>"
        ),
        parse_mode="HTML",
        reply_markup=income_schedule_keyboard(),
    )


def _parse_name_and_amount(text: str) -> tuple[str, Decimal] | None:
    """Parse "name + amount" or "amount + name" — split at the first
    digit run. Reuses ``parse_amount`` for VND-friendly suffixes (tr,
    triệu, k, etc.).

    We don't reuse ``wealth.amount_parser.parse_label_and_amount``
    because it strips bracket-form labels in a way that's wrong for
    "Cổ tức VNM" (would lose the ticker)."""
    text = text.strip()
    if not text:
        return None

    # Find the first character that introduces a number.
    digit_idx = -1
    for i, ch in enumerate(text):
        if ch.isdigit():
            digit_idx = i
            break
    if digit_idx < 0:
        return None

    name = text[:digit_idx].strip(" ,.:")
    amount_part = text[digit_idx:].strip()
    if not name:
        return None

    amount = parse_amount(amount_part)
    if amount is None:
        return None
    return name, amount


async def _handle_schedule_pick(
    db: AsyncSession, chat_id: int, user: User, schedule: str, draft: dict,
) -> None:
    """Step 3: based on schedule, route to the right follow-up."""
    valid = {s.value for s in ScheduleType}
    if schedule not in valid:
        await send_message(chat_id=chat_id, text="Lịch không hợp lệ.")
        return

    if schedule == ScheduleType.MONTHLY.value:
        await wizard_service.update_step(
            db, user.id, step="schedule_day",
            draft_patch={"schedule_type": schedule},
        )
        await send_message(
            chat_id=chat_id,
            text=(
                "📅 <b>Ngày nào trong tháng?</b>\n\n"
                "Số từ 1-31. Gõ <code>0</code> nếu không cố định."
            ),
            parse_mode="HTML",
        )
        return

    if schedule == ScheduleType.ANNUALLY.value:
        await wizard_service.update_step(
            db, user.id, step="schedule_month",
            draft_patch={"schedule_type": schedule},
        )
        await send_message(
            chat_id=chat_id,
            text="🗓️ <b>Tháng nào trong năm?</b>",
            parse_mode="HTML",
            reply_markup=income_month_keyboard(),
        )
        return

    # Quarterly / ad_hoc: skip directly to start_date.
    await wizard_service.update_step(
        db, user.id, step="start_date",
        draft_patch={"schedule_type": schedule},
    )
    await _prompt_start_date(chat_id)


async def _handle_schedule_day_input(
    db: AsyncSession, chat_id: int, user: User, text: str, draft: dict,
) -> None:
    """Step 4 (monthly): day of month. ``0`` means "không cố định"
    (skip — wizard saves with day=None). Anything else must be 1-31."""
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
        db, user.id, step="start_date",
        draft_patch={"schedule_day": day},
    )
    await _prompt_start_date(chat_id)


async def _handle_schedule_month_pick(
    db: AsyncSession, chat_id: int, user: User, month_str: str, draft: dict,
) -> None:
    try:
        month = int(month_str)
    except ValueError:
        await send_message(chat_id=chat_id, text="Tháng không hợp lệ.")
        return
    if not 1 <= month <= 12:
        await send_message(chat_id=chat_id, text="Tháng phải từ 1-12.")
        return

    await wizard_service.update_step(
        db, user.id, step="start_date",
        draft_patch={"schedule_month": month},
    )
    await _prompt_start_date(chat_id)


async def _prompt_start_date(chat_id: int) -> None:
    await send_message(
        chat_id=chat_id,
        text="📆 <b>Ngày bắt đầu?</b>",
        parse_mode="HTML",
        reply_markup=income_start_date_keyboard(),
    )


async def _handle_start_date_pick(
    db: AsyncSession, chat_id: int, user: User, choice: str, draft: dict,
) -> None:
    if choice == "today":
        await _commit_create(db, chat_id, user, {**draft, "start_date_iso": date.today().isoformat()})
        return
    if choice == "custom":
        await wizard_service.update_step(db, user.id, step="start_date_input")
        await send_message(
            chat_id=chat_id,
            text=(
                "✏️ <b>Ngày bắt đầu?</b>\n\n"
                "Format: <code>YYYY-MM-DD</code>\n"
                "Ví dụ: <code>2024-01-15</code>"
            ),
            parse_mode="HTML",
        )


async def _handle_start_date_input(
    db: AsyncSession, chat_id: int, user: User, text: str, draft: dict,
) -> None:
    cleaned = text.strip()
    try:
        d = date.fromisoformat(cleaned)
    except ValueError:
        await send_message(
            chat_id=chat_id,
            text="Format: <code>YYYY-MM-DD</code>. Ví dụ: <code>2024-01-15</code>",
            parse_mode="HTML",
        )
        return
    await _commit_create(db, chat_id, user, {**draft, "start_date_iso": d.isoformat()})


async def _commit_create(
    db: AsyncSession, chat_id: int, user: User, draft: dict,
) -> None:
    """Final step: validate via Pydantic, save, confirm."""
    try:
        payload = IncomeStreamCreate(
            name=draft["name"],
            stream_type=draft["stream_type"],
            amount=Decimal(str(draft["amount"])),
            schedule_type=draft["schedule_type"],
            schedule_day=draft.get("schedule_day"),
            schedule_month=draft.get("schedule_month"),
            start_date=date.fromisoformat(draft["start_date_iso"]),
            is_passive=draft.get("is_passive"),
        )
    except Exception as exc:
        logger.warning("income_stream payload invalid: %s draft=%s", exc, draft)
        await wizard_service.clear(db, user.id)
        await send_message(
            chat_id=chat_id,
            text="Có gì đó chưa đúng — bạn thử lại từ đầu nhé.",
        )
        return

    stream = await income_service.create_income_stream(db, user.id, payload)
    await wizard_service.clear(db, user.id)
    analytics.track(
        IncomeEvent.STREAM_ADDED, user_id=user.id,
        properties={
            "stream_type": stream.stream_type,
            "schedule_type": stream.schedule_type,
            "is_passive": stream.is_passive,
        },
    )

    icon = get_icon(stream.stream_type)
    sched = _schedule_label(stream.schedule_type)
    monthly_eq = stream.monthly_equivalent
    extra_line = ""
    if stream.schedule_type != "monthly":
        extra_line = (
            f"\n   ≈ <b>{format_money_short(monthly_eq)}/tháng</b> tạm tính"
        )
    await send_message(
        chat_id=chat_id,
        text=(
            f"✅ Đã thêm {icon} <b>{stream.name}</b>\n"
            f"   {format_money_short(stream.amount)}/{sched}"
            f"{extra_line}"
        ),
        parse_mode="HTML",
    )
    # Refresh threshold based on new income (best-effort).
    try:
        from backend.wealth.services import threshold_service
        await threshold_service.update_user_thresholds(db, user.id)
    except Exception:
        logger.exception("threshold refresh failed after income add")


# ---------- Edit flow (amount-only for Epic 2) -----------------------


async def _handle_edit_pick(
    db: AsyncSession, chat_id: int, user: User, stream_id_str: str,
) -> None:
    """Edit-amount-only sub-wizard. Full edit (rename, schedule
    change) is Phase 4 — Epic 2 keeps to the most-asked operation."""
    try:
        stream_id = uuid.UUID(stream_id_str)
    except ValueError:
        await send_message(chat_id=chat_id, text="Không tìm thấy nguồn thu.")
        return
    stream = await income_service.get_stream_by_id(db, user.id, stream_id)
    if stream is None:
        await send_message(chat_id=chat_id, text="Không tìm thấy nguồn thu.")
        return

    await wizard_service.start_flow(
        db, user.id, FLOW_EDIT, step="amount",
        draft={"stream_id": str(stream_id), "name": stream.name},
    )
    sched = _schedule_label(stream.schedule_type)
    await send_message(
        chat_id=chat_id,
        text=(
            f"✏️ Sửa <b>{stream.name}</b>\n\n"
            f"Số tiền hiện tại: <b>{format_money_short(stream.amount)}/{sched}</b>\n\n"
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
            chat_id=chat_id,
            text="Mình chưa hiểu. Ví dụ: <code>32tr</code>",
            parse_mode="HTML",
        )
        return

    try:
        stream_id = uuid.UUID(str(draft.get("stream_id")))
    except (TypeError, ValueError):
        await wizard_service.clear(db, user.id)
        await send_message(chat_id=chat_id, text="Có lỗi với wizard.")
        return

    await income_service.update_income_stream(
        db, user.id, stream_id,
        IncomeStreamUpdate(amount=Decimal(amount)),
    )
    await wizard_service.clear(db, user.id)
    analytics.track(
        IncomeEvent.STREAM_UPDATED, user_id=user.id,
        properties={"field": "amount"},
    )
    await send_message(
        chat_id=chat_id,
        text=f"✅ Đã cập nhật: <b>{format_money_short(amount)}</b>",
        parse_mode="HTML",
    )

    try:
        from backend.wealth.services import threshold_service
        await threshold_service.update_user_thresholds(db, user.id)
    except Exception:
        logger.exception("threshold refresh failed after income edit")


# ---------- Delete / Pause / Resume callbacks -----------------------


async def _handle_delete(
    db: AsyncSession, chat_id: int, user: User, stream_id_str: str,
) -> None:
    """Show 2-tap confirm to avoid accidental deletes."""
    try:
        uuid.UUID(stream_id_str)
    except ValueError:
        await send_message(chat_id=chat_id, text="Không tìm thấy nguồn thu.")
        return
    await send_message(
        chat_id=chat_id,
        text=(
            "🗑️ <b>Xoá nguồn thu này?</b>\n"
            "Hành động không thể hoàn tác."
        ),
        parse_mode="HTML",
        reply_markup=income_delete_confirm_keyboard(stream_id_str),
    )


async def _handle_delete_confirm(
    db: AsyncSession, chat_id: int, user: User, stream_id_str: str,
) -> None:
    try:
        stream_id = uuid.UUID(stream_id_str)
    except ValueError:
        await send_message(chat_id=chat_id, text="Không tìm thấy nguồn thu.")
        return
    deleted = await income_service.delete_stream(db, user.id, stream_id)
    if not deleted:
        await send_message(chat_id=chat_id, text="Không tìm thấy nguồn thu.")
        return
    analytics.track(IncomeEvent.STREAM_DELETED, user_id=user.id)
    await send_message(chat_id=chat_id, text="🗑️ Đã xoá.")


async def _handle_pause(
    db: AsyncSession, chat_id: int, user: User, stream_id_str: str,
) -> None:
    try:
        stream_id = uuid.UUID(stream_id_str)
    except ValueError:
        await send_message(chat_id=chat_id, text="Không tìm thấy nguồn thu.")
        return
    try:
        await income_service.pause_stream(db, user.id, stream_id)
    except ValueError:
        await send_message(chat_id=chat_id, text="Không tìm thấy nguồn thu.")
        return
    analytics.track(IncomeEvent.STREAM_PAUSED, user_id=user.id)
    await send_message(chat_id=chat_id, text="⏸️ Đã tạm dừng.")


async def _handle_resume(
    db: AsyncSession, chat_id: int, user: User, stream_id_str: str,
) -> None:
    try:
        stream_id = uuid.UUID(stream_id_str)
    except ValueError:
        await send_message(chat_id=chat_id, text="Không tìm thấy nguồn thu.")
        return
    try:
        await income_service.resume_stream(db, user.id, stream_id)
    except ValueError:
        await send_message(chat_id=chat_id, text="Không tìm thấy nguồn thu.")
        return
    analytics.track(IncomeEvent.STREAM_RESUMED, user_id=user.id)
    await send_message(chat_id=chat_id, text="▶️ Đã bật lại.")


# ---------- Public dispatch ------------------------------------------


_TEXT_DISPATCH = {
    (FLOW_ADD, "amount"): _handle_amount_input,
    (FLOW_ADD, "schedule_day"): _handle_schedule_day_input,
    (FLOW_ADD, "start_date_input"): _handle_start_date_input,
    (FLOW_EDIT, "amount"): _handle_edit_amount_input,
}


async def handle_income_text_input(
    db: AsyncSession, message: dict,
) -> bool:
    """Consume free text if the user is mid-income-wizard.

    Returns True for *any* income flow — at button-step states (type,
    schedule, start_date) we send a "tap a button" nudge so stray
    text doesn't leak into the NL parser. Same defensive behaviour
    as ``asset_entry.handle_asset_text_input``.
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
    if not (flow or "").startswith("income_"):
        return False

    handler = _TEXT_DISPATCH.get((flow, step))
    if handler is None:
        analytics.track(
            IncomeEvent.PARSE_FAILED, user_id=user.id,
            properties={"flow": flow, "step": step,
                        "reason": "text_at_button_step"},
        )
        await send_message(
            chat_id=chat_id,
            text=(
                "👆 Bạn đang trong wizard <b>thu nhập</b> — "
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
            "income wizard text handler crashed: flow=%s step=%s",
            flow, step,
        )
        await wizard_service.clear(db, user.id)
        await send_message(
            chat_id=chat_id,
            text="Có lỗi xảy ra, mình huỷ wizard. Thử /menu lại nhé.",
        )
    return True


async def _dispatch(
    db: AsyncSession, chat_id: int, user: User,
    action: str, arg: str | None,
) -> None:
    """Body of the callback dispatcher — split out so we can run it
    in parallel with answer_callback (matches asset_entry pattern)."""
    if action == "start":
        await start_income_wizard(db, chat_id, user)
        return
    if action == "cancel":
        await wizard_service.clear(db, user.id)
        analytics.track(IncomeEvent.WIZARD_CANCELED, user_id=user.id)
        await send_message(chat_id=chat_id, text="Đã huỷ. 👋")
        return
    if action == "list":
        await show_income_list(db, chat_id, user)
        return

    draft = wizard_service.get_draft(user.wizard_state)

    if action == "type" and arg:
        await _handle_type_pick(db, chat_id, user, arg)
        return
    if action == "schedule" and arg:
        await _handle_schedule_pick(db, chat_id, user, arg, draft)
        return
    if action == "month" and arg:
        await _handle_schedule_month_pick(db, chat_id, user, arg, draft)
        return
    if action == "start_date" and arg:
        await _handle_start_date_pick(db, chat_id, user, arg, draft)
        return

    if action == "edit" and arg:
        await _handle_edit_pick(db, chat_id, user, arg)
        return
    if action == "delete" and arg:
        await _handle_delete(db, chat_id, user, arg)
        return
    if action == "delete_confirm" and arg:
        await _handle_delete_confirm(db, chat_id, user, arg)
        return
    if action == "pause" and arg:
        await _handle_pause(db, chat_id, user, arg)
        return
    if action == "resume" and arg:
        await _handle_resume(db, chat_id, user, arg)
        return


async def handle_income_callback(
    db: AsyncSession, callback_query: dict,
) -> bool:
    """Route any ``income:*`` callback. Returns True if handled."""
    data: str = callback_query.get("data") or ""
    if not data.startswith(f"{CB_INCOME}:") and data != CB_INCOME:
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

    await asyncio.gather(
        answer_callback(callback_id),
        _dispatch(db, chat_id, user, action, arg),
    )
    return True
