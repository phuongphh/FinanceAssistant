"""Goals wizard + list view + reminder action handlers (Phase 3.8 Epic 5).

Single ``goals:*`` callback prefix; mirrors the income / recurring
handlers' shape. Flows:

    goals_add    — template → (custom name?) → amount → date → save
    goals_edit_progress — text amount → update_goal_progress
    goals_edit_amount   — text amount → update_goal target_amount
    goals_edit_date     — text YYYY-MM-DD or skip → update_goal target_date

Uses ``GoalProjectionService.project_goal_with_savings`` to render
a live preview after the date step so the user sees feasibility
before saving.

Layer contract: handler reads/mutates DB through services, never
commits — worker owns the transaction boundary.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from backend import analytics
from backend.bot.formatters.money import format_money_short
from backend.bot.keyboards.common import parse_callback
from backend.bot.keyboards.goals_keyboard import (
    CB_GOALS,
    goals_date_keyboard,
    goals_delete_confirm_keyboard,
    goals_list_actions_keyboard,
    goals_list_footer_keyboard,
    goals_save_keyboard,
    goals_template_keyboard,
)
from backend.models.goal import Goal
from backend.bot.utils.emoji_animation import message_kwargs_for_animation
from backend.models.user import User
from backend.schemas.goal import (
    FeasibilityBand,
    GoalCreate,
    GoalProgressUpdate,
    GoalUpdate,
)
from backend.services import (
    goal_projection,
    goal_service,
    goal_templates,
    wizard_service,
)
from backend.services.dashboard_service import get_user_by_telegram_id
from backend.services.telegram_service import answer_callback, send_message
from backend.wealth.amount_parser import has_negative_sign, parse_amount

logger = logging.getLogger(__name__)


class GoalEvent:
    WIZARD_OPENED = "goal_wizard_opened"
    TEMPLATE_PICKED = "goal_template_picked"
    GOAL_ADDED = "goal_added"
    GOAL_UPDATED = "goal_updated"
    GOAL_DELETED = "goal_deleted"
    PROGRESS_UPDATED = "goal_progress_updated"
    WIZARD_CANCELED = "goal_wizard_canceled"
    PARSE_FAILED = "goal_wizard_parse_failed"


# Flow / step names persisted in wizard_state. ``goal_*`` prefix so
# the worker's text-input dispatcher isolates them.
FLOW_ADD = "goal_add"
FLOW_EDIT_PROGRESS = "goal_edit_progress"
FLOW_EDIT_AMOUNT = "goal_edit_amount"
FLOW_EDIT_DATE = "goal_edit_date"


_DATE_PRESETS_DAYS = {
    "6m": 30 * 6,
    "1y": 365,
    "2y": 365 * 2,
    "3y": 365 * 3,
    "5y": 365 * 5,
}

_FEASIBILITY_LABELS = {
    FeasibilityBand.EASY.value: "🌱 Dễ đạt",
    FeasibilityBand.FEASIBLE.value: "👍 Khả thi",
    FeasibilityBand.STRETCH.value: "💪 Thử thách",
    FeasibilityBand.AMBITIOUS.value: "🎯 Tham vọng",
    FeasibilityBand.NEEDS_REVISION.value: "🤔 Cần điều chỉnh",
    FeasibilityBand.UNKNOWN.value: "ℹ️ Chưa đủ dữ liệu",
}


# ---------- List view ------------------------------------------------


async def show_goals_list(
    db: AsyncSession,
    chat_id: int,
    user: User,
    *,
    back_callback: str = "menu:main",
    back_label: str = "◀️ Quay về menu",
) -> None:
    """Render menu:goals:list — active goals with progress bars +
    per-row action buttons. Empty state if no goals."""
    goals = await goal_service.list_goals(db, user.id, active_only=True)
    if not goals:
        await send_message(
            chat_id=chat_id,
            text=(
                "🎯 <b>Mục tiêu của bạn</b>\n\n"
                "Chưa có mục tiêu nào! Mục tiêu đầu tiên của bạn là gì?"
            ),
            parse_mode="HTML",
            reply_markup=goals_list_footer_keyboard(
                back_callback=back_callback, back_label=back_label
            ),
        )
        return

    await send_message(
        chat_id=chat_id,
        text=f"🎯 <b>Mục tiêu của bạn</b> ({len(goals)} mục)",
        parse_mode="HTML",
    )

    for g in goals:
        await send_message(
            chat_id=chat_id,
            text=_format_goal_row(g),
            parse_mode="HTML",
            reply_markup=goals_list_actions_keyboard(g.id),
        )

    await send_message(
        chat_id=chat_id, text="—",
        reply_markup=goals_list_footer_keyboard(
            back_callback=back_callback, back_label=back_label
        ),
    )


def _format_goal_row(goal: Goal) -> str:
    """One goal in the list view: icon + name + progress bar + amount.

    Progress bar uses ▓ (filled) and ░ (empty) glyphs — both render
    consistent-width on Telegram's monospace fallback. 10-char bar
    keeps the message terse."""
    pct = goal.progress_pct
    filled = min(10, int(pct / 10))
    bar = "▓" * filled + "░" * (10 - filled)
    icon = goal.icon or goal_templates.get_icon(goal.template_id)
    deadline_line = ""
    if goal.target_date:
        deadline_line = f"\n   📅 Hạn: {goal.target_date.strftime('%d/%m/%Y')}"
    required_line = ""
    if goal.monthly_savings_required:
        required_line = (
            f"\n   💰 Cần "
            f"{format_money_short(goal.monthly_savings_required)}/tháng"
        )
    return (
        f"{icon} <b>{goal.name}</b>\n"
        f"   {bar} {pct:.0f}%\n"
        f"   {format_money_short(goal.current_amount)} / "
        f"{format_money_short(goal.target_amount)}"
        f"{deadline_line}"
        f"{required_line}"
    )


# ---------- Add flow ------------------------------------------------


async def start_goals_wizard(
    db: AsyncSession, chat_id: int, user: User
) -> None:
    await wizard_service.start_flow(
        db, user.id, FLOW_ADD, step="template", draft={},
    )
    await send_message(
        chat_id=chat_id,
        text=(
            "🎯 <b>Thêm mục tiêu mới</b>\n\n"
            "Bạn muốn đặt mục tiêu gì? Chọn template hoặc tự tạo:"
        ),
        parse_mode="HTML",
        reply_markup=goals_template_keyboard(),
    )
    analytics.track(GoalEvent.WIZARD_OPENED, user_id=user.id)


async def _send_goals_submenu(chat_id: int, user: User) -> None:
    """Navigate back to the goals submenu (4-button screen)."""
    from backend.bot.formatters.menu_formatter import format_submenu, get_submenu_hint
    level = user.wealth_level if user else None
    text, keyboard = format_submenu(user, "goals", level=level)
    hint = get_submenu_hint("goals")
    if hint:
        text = f"{text}\n\n{hint}"
    await send_message(chat_id=chat_id, text=text, reply_markup=keyboard)


async def cancel_wizard(
    db: AsyncSession, chat_id: int, user: User
) -> bool:
    flow = (user.wizard_state or {}).get("flow") or ""
    if not flow.startswith("goal_"):
        return False
    await wizard_service.clear(db, user.id)
    analytics.track(GoalEvent.WIZARD_CANCELED, user_id=user.id)
    await _send_goals_submenu(chat_id, user)
    return True


async def _handle_template_pick(
    db: AsyncSession, chat_id: int, user: User, template_id: str,
) -> None:
    template = goal_templates.get_template(template_id)
    if template is None:
        await send_message(chat_id=chat_id, text="Template không hợp lệ.")
        return
    analytics.track(
        GoalEvent.TEMPLATE_PICKED, user_id=user.id,
        properties={"template_id": template_id},
    )
    await wizard_service.update_step(
        db, user.id, step="amount",
        draft_patch={
            "template_id": template.id,
            "icon": template.icon,
            "name": template.name,
        },
    )
    range_hint = (
        f"Thường: {format_money_short(template.min_amount)} - "
        f"{format_money_short(template.max_amount)}"
    )
    await send_message(
        chat_id=chat_id,
        text=(
            f"{template.icon} <b>{template.name}</b>\n\n"
            "💰 <b>Số tiền mục tiêu?</b>\n\n"
            f"{range_hint}\n"
            "Ví dụ: <code>800tr</code>, <code>1.5 tỷ</code>"
        ),
        parse_mode="HTML",
    )


async def _handle_custom_pick(
    db: AsyncSession, chat_id: int, user: User,
) -> None:
    """User chose "Tự tạo" — collect a name first, then amount."""
    await wizard_service.update_step(
        db, user.id, step="custom_name", draft_patch={},
    )
    await send_message(
        chat_id=chat_id,
        text=(
            "✏️ <b>Mục tiêu tự tạo</b>\n\n"
            "Tên mục tiêu? Ví dụ: <code>Mua máy ảnh</code>, "
            "<code>Quà sinh nhật</code>"
        ),
        parse_mode="HTML",
    )


async def _handle_custom_name_input(
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
        db, user.id, step="amount",
        draft_patch={"name": name, "icon": "🎯", "template_id": None},
    )
    await send_message(
        chat_id=chat_id,
        text=(
            f"✏️ <b>{name}</b>\n\n"
            "💰 <b>Số tiền mục tiêu?</b>\n\n"
            "Ví dụ: <code>50tr</code>, <code>500tr</code>"
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
            GoalEvent.PARSE_FAILED, user_id=user.id,
            properties={"flow": FLOW_ADD, "field": "amount"},
        )
        await send_message(
            chat_id=chat_id,
            text=(
                "Mình chưa hiểu 😅\n"
                "Ví dụ: <code>800tr</code>, <code>1.5 tỷ</code>"
            ),
            parse_mode="HTML",
        )
        return

    await wizard_service.update_step(
        db, user.id, step="date",
        draft_patch={"target_amount": float(amount)},
    )
    await send_message(
        chat_id=chat_id,
        text=(
            f"✅ Target: <b>{format_money_short(amount)}</b>\n\n"
            "📅 <b>Khi nào muốn đạt được?</b> "
            "(Để trống nếu không định)"
        ),
        parse_mode="HTML",
        reply_markup=goals_date_keyboard(),
    )


async def _handle_date_pick(
    db: AsyncSession, chat_id: int, user: User, choice: str, draft: dict,
) -> None:
    if choice == "skip":
        await wizard_service.update_step(
            db, user.id, step="preview",
            draft_patch={"target_date_iso": None},
        )
        await _show_preview(db, chat_id, user)
        return

    if choice == "custom":
        await wizard_service.update_step(
            db, user.id, step="date_input",
        )
        await send_message(
            chat_id=chat_id,
            text=(
                "✏️ <b>Ngày target?</b>\n\n"
                "Format: <code>YYYY-MM-DD</code>\n"
                "Ví dụ: <code>2028-12-31</code>"
            ),
            parse_mode="HTML",
        )
        return

    days = _DATE_PRESETS_DAYS.get(choice)
    if days is None:
        await send_message(chat_id=chat_id, text="Lựa chọn không hợp lệ.")
        return
    target_date = date.today() + timedelta(days=days)
    await wizard_service.update_step(
        db, user.id, step="preview",
        draft_patch={"target_date_iso": target_date.isoformat()},
    )
    await _show_preview(db, chat_id, user)


async def _handle_date_input(
    db: AsyncSession, chat_id: int, user: User, text: str, draft: dict,
) -> None:
    cleaned = text.strip()
    try:
        target_date = date.fromisoformat(cleaned)
    except ValueError:
        await send_message(
            chat_id=chat_id,
            text="Format: <code>YYYY-MM-DD</code>. Ví dụ: <code>2028-12-31</code>",
            parse_mode="HTML",
        )
        return
    if target_date <= date.today():
        await send_message(
            chat_id=chat_id, text="Hạn phải sau hôm nay nhé 🙂",
        )
        return
    await wizard_service.update_step(
        db, user.id, step="preview",
        draft_patch={"target_date_iso": target_date.isoformat()},
    )
    await _show_preview(db, chat_id, user)


async def _show_preview(
    db: AsyncSession, chat_id: int, user: User,
) -> None:
    """Render the projection summary + save/back keyboard before
    the actual create. Spec § 2.2 example flow Q4 → Q5."""
    user = await _refresh_user(db, user)
    draft = wizard_service.get_draft(user.wizard_state)
    target_amount = Decimal(str(draft.get("target_amount") or 0))
    if target_amount <= 0:
        await wizard_service.clear(db, user.id)
        await send_message(chat_id=chat_id, text="Có lỗi với wizard.")
        return

    target_date_iso = draft.get("target_date_iso")
    target_date = date.fromisoformat(target_date_iso) if target_date_iso else None

    # Build a lightweight Goal-like object for the projection helper.
    avg_savings = await goal_projection.get_avg_monthly_savings(db, user.id)

    name = draft.get("name") or "Mục tiêu"
    icon = draft.get("icon") or "🎯"

    # Inline projection (no DB row yet — we synthesise a Goal stub).
    stub = Goal()
    stub.id = uuid.uuid4()
    stub.user_id = user.id
    stub.name = name
    stub.icon = icon
    stub.template_id = draft.get("template_id")
    stub.target_amount = target_amount
    stub.current_amount = Decimal(0)
    stub.target_date = target_date
    stub.monthly_savings_required = None
    stub.status = "active"
    stub.priority = 5
    projection = goal_projection.project_goal_with_savings(
        stub, avg_savings,
    )

    lines = [
        f"{icon} <b>{name}</b>",
        f"💰 Target: <b>{format_money_short(target_amount)}</b>",
    ]
    if target_date:
        lines.append(f"📅 Hạn: <b>{target_date.strftime('%d/%m/%Y')}</b>")
    else:
        lines.append("📅 Hạn: <i>Bỏ qua (open-ended)</i>")
    lines.append("")

    if projection.required_monthly_savings:
        lines.append(
            f"Cần tiết kiệm: <b>"
            f"{format_money_short(projection.required_monthly_savings)}/tháng</b>"
        )
        if projection.avg_monthly_savings:
            lines.append(
                f"Hiện tại tiết kiệm: "
                f"~{format_money_short(projection.avg_monthly_savings)}/tháng"
            )
        if projection.feasibility:
            label = _FEASIBILITY_LABELS.get(
                projection.feasibility, projection.feasibility,
            )
            lines.append(f"Đánh giá: <b>{label}</b>")

    if projection.estimated_completion_date:
        lines.append(
            "Dự kiến đạt: "
            f"<b>{projection.estimated_completion_date.strftime('%d/%m/%Y')}</b>"
        )
    if projection.notes:
        lines.append("")
        for n in projection.notes:
            lines.append(f"• {n}")

    await send_message(
        chat_id=chat_id,
        text="\n".join(lines),
        parse_mode="HTML",
        reply_markup=goals_save_keyboard(),
    )


async def _handle_save(
    db: AsyncSession, chat_id: int, user: User,
) -> None:
    user = await _refresh_user(db, user)
    draft = wizard_service.get_draft(user.wizard_state)
    target_amount = Decimal(str(draft.get("target_amount") or 0))
    target_date_iso = draft.get("target_date_iso")
    if target_amount <= 0:
        await wizard_service.clear(db, user.id)
        await send_message(chat_id=chat_id, text="Có lỗi với wizard.")
        return
    target_date = date.fromisoformat(target_date_iso) if target_date_iso else None

    payload = GoalCreate(
        name=draft.get("name") or "Mục tiêu",
        target_amount=target_amount,
        target_date=target_date,
        template_id=draft.get("template_id"),
        icon=draft.get("icon"),
    )
    goal = await goal_service.create_goal(db, user.id, payload)

    # Cache the projection's required_monthly_savings on the row so
    # the list view doesn't recompute on every render.
    avg_savings = await goal_projection.get_avg_monthly_savings(db, user.id)
    projection = goal_projection.project_goal_with_savings(
        goal, avg_savings,
    )
    if projection.required_monthly_savings is not None:
        goal.monthly_savings_required = projection.required_monthly_savings

    await wizard_service.clear(db, user.id)
    analytics.track(
        GoalEvent.GOAL_ADDED, user_id=user.id,
        properties={
            "template_id": goal.template_id,
            "has_target_date": goal.target_date is not None,
            "feasibility": (
                projection.feasibility
                if projection.feasibility else None
            ),
        },
    )

    await send_message(
        chat_id=chat_id,
        text=(
            f"✅ Đã lưu {goal.icon or '🎯'} <b>{goal.name}</b>\n\n"
            f"Mở /menu → 🎯 Mục tiêu để theo dõi tiến độ."
        ),
        parse_mode="HTML",
    )


# ---------- Edit progress / amount / date sub-wizards ----------------


async def _handle_edit_progress_pick(
    db: AsyncSession, chat_id: int, user: User, goal_id_str: str,
) -> None:
    try:
        goal_id = uuid.UUID(goal_id_str)
    except ValueError:
        await send_message(chat_id=chat_id, text="Không tìm thấy mục tiêu.")
        return
    goal = await goal_service.get_goal(db, user.id, goal_id)
    if goal is None:
        await send_message(chat_id=chat_id, text="Không tìm thấy mục tiêu.")
        return
    await wizard_service.start_flow(
        db, user.id, FLOW_EDIT_PROGRESS, step="amount",
        draft={"goal_id": str(goal_id)},
    )
    await send_message(
        chat_id=chat_id,
        text=(
            f"💰 Cập nhật tiến độ <b>{goal.name}</b>\n\n"
            f"Hiện tại: {format_money_short(goal.current_amount)} / "
            f"{format_money_short(goal.target_amount)}\n\n"
            "<b>Số tiền mới đã có?</b> (tổng, không phải delta)"
        ),
        parse_mode="HTML",
    )


async def _handle_edit_progress_input(
    db: AsyncSession, chat_id: int, user: User, text: str, draft: dict,
) -> None:
    if has_negative_sign(text):
        await send_message(chat_id=chat_id, text="Số tiền phải ≥ 0.")
        return
    amount = parse_amount(text)
    if amount is None or amount < 0:
        await send_message(
            chat_id=chat_id,
            text="Mình chưa hiểu. Ví dụ: <code>200tr</code>",
            parse_mode="HTML",
        )
        return
    try:
        goal_id = uuid.UUID(str(draft.get("goal_id")))
    except (TypeError, ValueError):
        await wizard_service.clear(db, user.id)
        await send_message(chat_id=chat_id, text="Có lỗi với wizard.")
        return

    updated = await goal_service.update_goal_progress(
        db, user.id, goal_id, GoalProgressUpdate(current_amount=Decimal(amount)),
    )
    await wizard_service.clear(db, user.id)
    if updated is None:
        await send_message(chat_id=chat_id, text="Không tìm thấy mục tiêu.")
        return

    analytics.track(
        GoalEvent.PROGRESS_UPDATED, user_id=user.id,
        properties={"goal_id": str(goal_id)},
    )

    if updated.is_completed:
        msg = (
            f"🎉 Đạt mục tiêu {updated.name}!\n\n"
            f"Chúc mừng — bạn đã hoàn thành "
            f"{format_money_short(updated.target_amount)}."
        )
        await send_message(
            chat_id=chat_id,
            text=msg,
            parse_mode=None,
            **message_kwargs_for_animation(msg, "milestones"),
        )
        return

    avg_savings = await goal_projection.get_avg_monthly_savings(db, user.id)
    projection = goal_projection.project_goal_with_savings(updated, avg_savings)
    eta_line = ""
    if projection.estimated_completion_date:
        eta_line = (
            f"\nDự kiến đạt: "
            f"{projection.estimated_completion_date.strftime('%d/%m/%Y')}"
        )
    elif projection.months_remaining and projection.required_monthly_savings:
        eta_line = (
            f"\nCần {format_money_short(projection.required_monthly_savings)}/tháng "
            f"trong {projection.months_remaining} tháng."
        )
    await send_message(
        chat_id=chat_id,
        text=(
            f"✅ Đã update.\n"
            f"Còn cần "
            f"{format_money_short(projection.remaining_amount)} để hoàn thành."
            f"{eta_line}"
        ),
        parse_mode="HTML",
    )


async def _handle_edit_amount_pick(
    db: AsyncSession, chat_id: int, user: User, goal_id_str: str,
) -> None:
    try:
        goal_id = uuid.UUID(goal_id_str)
    except ValueError:
        await send_message(chat_id=chat_id, text="Không tìm thấy mục tiêu.")
        return
    goal = await goal_service.get_goal(db, user.id, goal_id)
    if goal is None:
        await send_message(chat_id=chat_id, text="Không tìm thấy mục tiêu.")
        return
    await wizard_service.start_flow(
        db, user.id, FLOW_EDIT_AMOUNT, step="amount",
        draft={"goal_id": str(goal_id)},
    )
    await send_message(
        chat_id=chat_id,
        text=(
            f"🎯 Sửa target <b>{goal.name}</b>\n\n"
            f"Target hiện tại: {format_money_short(goal.target_amount)}\n\n"
            "Nhập target mới:"
        ),
        parse_mode="HTML",
    )


async def _handle_edit_amount_input(
    db: AsyncSession, chat_id: int, user: User, text: str, draft: dict,
) -> None:
    if has_negative_sign(text):
        await send_message(chat_id=chat_id, text="Số tiền phải > 0.")
        return
    amount = parse_amount(text)
    if amount is None or amount <= 0:
        await send_message(
            chat_id=chat_id,
            text="Mình chưa hiểu. Ví dụ: <code>900tr</code>",
            parse_mode="HTML",
        )
        return
    try:
        goal_id = uuid.UUID(str(draft.get("goal_id")))
    except (TypeError, ValueError):
        await wizard_service.clear(db, user.id)
        await send_message(chat_id=chat_id, text="Có lỗi với wizard.")
        return
    await goal_service.update_goal(
        db, user.id, goal_id,
        GoalUpdate(target_amount=Decimal(amount)),
    )
    await wizard_service.clear(db, user.id)
    analytics.track(
        GoalEvent.GOAL_UPDATED, user_id=user.id,
        properties={"field": "target_amount"},
    )
    await send_message(
        chat_id=chat_id,
        text=f"✅ Target mới: <b>{format_money_short(amount)}</b>",
        parse_mode="HTML",
    )


async def _handle_edit_date_pick(
    db: AsyncSession, chat_id: int, user: User, goal_id_str: str,
) -> None:
    try:
        goal_id = uuid.UUID(goal_id_str)
    except ValueError:
        await send_message(chat_id=chat_id, text="Không tìm thấy mục tiêu.")
        return
    goal = await goal_service.get_goal(db, user.id, goal_id)
    if goal is None:
        await send_message(chat_id=chat_id, text="Không tìm thấy mục tiêu.")
        return
    await wizard_service.start_flow(
        db, user.id, FLOW_EDIT_DATE, step="date_input",
        draft={"goal_id": str(goal_id)},
    )
    current_line = (
        f"\nHạn hiện tại: {goal.target_date.strftime('%d/%m/%Y')}"
        if goal.target_date else "\nHiện tại: chưa có hạn"
    )
    await send_message(
        chat_id=chat_id,
        text=(
            f"📅 Sửa hạn <b>{goal.name}</b>{current_line}\n\n"
            "Nhập hạn mới (<code>YYYY-MM-DD</code>) hoặc gõ "
            "<code>skip</code> để bỏ hạn:"
        ),
        parse_mode="HTML",
    )


async def _handle_edit_date_input(
    db: AsyncSession, chat_id: int, user: User, text: str, draft: dict,
) -> None:
    cleaned = text.strip().lower()
    target_date: date | None = None
    if cleaned not in ("skip", "bỏ qua", "bo qua"):
        try:
            target_date = date.fromisoformat(text.strip())
        except ValueError:
            await send_message(
                chat_id=chat_id,
                text="Format: <code>YYYY-MM-DD</code> hoặc <code>skip</code>",
                parse_mode="HTML",
            )
            return
        if target_date <= date.today():
            await send_message(
                chat_id=chat_id,
                text="Ngày hoàn thành phải sau hôm nay nhé 🙂",
            )
            return
    try:
        goal_id = uuid.UUID(str(draft.get("goal_id")))
    except (TypeError, ValueError):
        await wizard_service.clear(db, user.id)
        await send_message(chat_id=chat_id, text="Có lỗi với wizard.")
        return
    updated = await goal_service.update_goal(
        db, user.id, goal_id,
        GoalUpdate(target_date=target_date),
    )
    if updated is None:
        await wizard_service.clear(db, user.id)
        await send_message(chat_id=chat_id, text="Không tìm thấy mục tiêu.")
        return

    # Issue #450 §2 — auto-recalculate required monthly savings + cache
    # so the list view shows the fresh figure without a separate
    # interaction. The cache column (``Goal.monthly_savings_required``)
    # is the source of truth for the list/dashboard readers.
    avg_savings = await goal_projection.get_avg_monthly_savings(db, user.id)
    projection = goal_projection.project_goal_with_savings(updated, avg_savings)
    updated.monthly_savings_required = projection.required_monthly_savings

    await wizard_service.clear(db, user.id)
    analytics.track(
        GoalEvent.GOAL_UPDATED, user_id=user.id,
        properties={"field": "target_date"},
    )
    await send_message(
        chat_id=chat_id,
        text=_format_date_change_summary(updated, projection),
        parse_mode="HTML",
    )


def _format_date_change_summary(
    goal: Goal, projection,
) -> str:
    """Issue #450 §2 — projection summary shown after a target_date
    edit. Branches on the spec'd edge cases (already met, no remaining
    months, open-ended) so the user always reads a coherent next step.
    """
    if goal.target_date is None:
        return "✅ Đã bỏ hạn — mục tiêu giờ là open-ended."

    date_line = (
        f"✅ Hạn mới: <b>{goal.target_date.strftime('%d/%m/%Y')}</b>"
    )

    # Already met — celebrate instead of computing required savings.
    if projection.remaining_amount <= 0:
        return (
            f"{date_line}\n\n"
            "🎉 Mục tiêu đã đạt — không cần tiết kiệm thêm."
        )

    # months_remaining == 0 means the target_date is so close that the
    # whole-month rounding floored to zero. Caller should treat this
    # as a lump-sum requirement.
    if projection.months_remaining == 0:
        return (
            f"{date_line}\n\n"
            "⚡ Cần hoàn thành ngay — hạn quá gần để chia theo tháng."
        )

    if projection.required_monthly_savings:
        lines = [
            date_line,
            "",
            (
                f"💰 Cần tiết kiệm "
                f"<b>{format_money_short(projection.required_monthly_savings)}"
                f"/tháng</b> để đạt mục tiêu vào "
                f"{goal.target_date.strftime('%d/%m/%Y')}."
            ),
        ]
        if projection.feasibility:
            label = _FEASIBILITY_LABELS.get(
                projection.feasibility, projection.feasibility,
            )
            lines.append(f"Đánh giá: <b>{label}</b>")
        return "\n".join(lines)

    return date_line


# ---------- Delete (2-tap) ------------------------------------------


async def _handle_delete_show_confirm(
    db: AsyncSession, chat_id: int, user: User, goal_id_str: str,
) -> None:
    try:
        uuid.UUID(goal_id_str)
    except ValueError:
        await send_message(chat_id=chat_id, text="Không tìm thấy mục tiêu.")
        return
    await send_message(
        chat_id=chat_id,
        text=(
            "🗑️ <b>Xoá mục tiêu này?</b>\n\n"
            "Hành động không thể hoàn tác. Nếu chỉ muốn tạm dừng, "
            "dùng menu khác."
        ),
        parse_mode="HTML",
        reply_markup=goals_delete_confirm_keyboard(goal_id_str),
    )


async def _handle_delete_confirm(
    db: AsyncSession, chat_id: int, user: User, goal_id_str: str,
) -> None:
    try:
        goal_id = uuid.UUID(goal_id_str)
    except ValueError:
        await send_message(chat_id=chat_id, text="Không tìm thấy mục tiêu.")
        return
    deleted = await goal_service.delete_goal(db, user.id, goal_id)
    if not deleted:
        await send_message(chat_id=chat_id, text="Không tìm thấy mục tiêu.")
        return
    analytics.track(GoalEvent.GOAL_DELETED, user_id=user.id)
    await send_message(chat_id=chat_id, text="🗑️ Đã xoá.")


# ---------- Public dispatch -----------------------------------------


_TEXT_DISPATCH = {
    (FLOW_ADD, "custom_name"): _handle_custom_name_input,
    (FLOW_ADD, "amount"): _handle_amount_input,
    (FLOW_ADD, "date_input"): _handle_date_input,
    (FLOW_EDIT_PROGRESS, "amount"): _handle_edit_progress_input,
    (FLOW_EDIT_AMOUNT, "amount"): _handle_edit_amount_input,
    (FLOW_EDIT_DATE, "date_input"): _handle_edit_date_input,
}


async def handle_goals_text_input(
    db: AsyncSession, message: dict,
) -> bool:
    """Consume free text if the user is mid-goals-wizard."""
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
    if not (flow or "").startswith("goal_"):
        return False

    handler = _TEXT_DISPATCH.get((flow, step))
    if handler is None:
        analytics.track(
            GoalEvent.PARSE_FAILED, user_id=user.id,
            properties={"flow": flow, "step": step,
                        "reason": "text_at_button_step"},
        )
        await send_message(
            chat_id=chat_id,
            text=(
                "👆 Bạn đang trong wizard <b>mục tiêu</b> — "
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
            "goals wizard text handler crashed: flow=%s step=%s",
            flow, step,
        )
        await wizard_service.clear(db, user.id)
        await send_message(
            chat_id=chat_id, text="Có lỗi xảy ra, mình huỷ wizard.",
        )
    return True


async def _dispatch(
    db: AsyncSession, chat_id: int, user: User,
    action: str, arg: str | None,
) -> None:
    if action == "start":
        await start_goals_wizard(db, chat_id, user)
        return
    if action == "list":
        await show_goals_list(db, chat_id, user)
        return
    if action == "cancel":
        await wizard_service.clear(db, user.id)
        analytics.track(GoalEvent.WIZARD_CANCELED, user_id=user.id)
        await _send_goals_submenu(chat_id, user)
        return
    if action == "custom":
        await _handle_custom_pick(db, chat_id, user)
        return
    if action == "save":
        await _handle_save(db, chat_id, user)
        return
    if action == "template" and arg:
        await _handle_template_pick(db, chat_id, user, arg)
        return
    draft = wizard_service.get_draft(user.wizard_state)
    if action == "date" and arg:
        await _handle_date_pick(db, chat_id, user, arg, draft)
        return
    if action == "edit_progress" and arg:
        await _handle_edit_progress_pick(db, chat_id, user, arg)
        return
    if action == "edit_amount" and arg:
        await _handle_edit_amount_pick(db, chat_id, user, arg)
        return
    if action == "edit_date" and arg:
        await _handle_edit_date_pick(db, chat_id, user, arg)
        return
    if action == "delete" and arg:
        await _handle_delete_show_confirm(db, chat_id, user, arg)
        return
    if action == "delete_confirm" and arg:
        await _handle_delete_confirm(db, chat_id, user, arg)
        return


async def handle_goals_callback(
    db: AsyncSession, callback_query: dict,
) -> bool:
    """Route any ``goals:*`` callback. Returns True if handled."""
    data: str = callback_query.get("data") or ""
    if not data.startswith(f"{CB_GOALS}:") and data != CB_GOALS:
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


# ---------- Helpers --------------------------------------------------


async def _refresh_user(db: AsyncSession, user: User) -> User:
    """Re-fetch the user so we read fresh ``wizard_state`` after an
    update_step call. The handler receives an old ``user`` snapshot
    from the worker; we need the latest draft for ``_show_preview``
    / ``_handle_save``.
    """
    refreshed = await db.get(User, user.id)
    return refreshed or user
