from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import time
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.formatters.money import format_money_short
from backend.bot.formatters.progress_bar import make_progress_bar
from backend.models.user import User
from backend.profile.models.user_profile import AGE_RANGES, UserProfile
from backend.profile.services.stats_aggregator import ProfileStatsAggregator
from backend.profile.services.wealth_level_mapper import WealthLevelMapper
from backend.services import wizard_service
from backend.services.telegram_service import (
    answer_callback,
    edit_message_text,
    send_message,
)

FLOW_PROFILE = "profile_edit"
STEP_DISPLAY_NAME = "awaiting_display_name"
STEP_NOTIFICATION_TIME = "awaiting_notification_time"
TIME_PRESETS = (time(6, 0), time(7, 0), time(8, 0), time(9, 0))
_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")
logger = logging.getLogger(__name__)

PROFILE_DEGRADED_NOTICE = (
    "_Mình đang hiển thị Profile ở chế độ an toàn; vài số liệu/cài đặt "
    "có thể tạm thời chưa cập nhật._"
)
PROFILE_SCHEMA_NOTICE = (
    "_Profile chưa sẵn sàng vì DB thiếu bảng profile; "
    "admin chạy `alembic upgrade head` nhé._"
)


@dataclass(frozen=True)
class ProfileUserSnapshot:
    """Stable user fields needed to render Profile after DB rollback.

    ``AsyncSession.rollback()`` expires ORM instances. The Profile fallback path
    must therefore snapshot user fields before any query that can fail; otherwise
    rendering the degraded profile can trigger another async lazy-load error.
    """

    id: Any
    display_name: str | None = None
    telegram_handle: str | None = None
    briefing_enabled: bool = True
    briefing_time: time | None = None


def profile_keyboard(
    *, editable: bool = True
) -> dict[str, list[list[dict[str, str]]]]:
    rows = []
    if editable:
        rows.extend(
            [
                [
                    {"text": "📝 Đổi tên hiển thị", "callback_data": "profile:edit_name"},
                    {"text": "🎂 Đổi nhóm tuổi", "callback_data": "profile:edit_age"},
                ],
                [{"text": "🔔 Cài thông báo", "callback_data": "profile:notifications"}],
            ]
        )
    rows.append([{"text": "◀️ Quay lại", "callback_data": "menu:main"}])
    return {"inline_keyboard": rows}


def age_keyboard() -> dict[str, list[list[dict[str, str]]]]:
    return {
        "inline_keyboard": [
            [
                {"text": "20-29", "callback_data": "profile:age:20-29"},
                {"text": "30-39", "callback_data": "profile:age:30-39"},
            ],
            [
                {"text": "40-49", "callback_data": "profile:age:40-49"},
                {"text": "50+", "callback_data": "profile:age:50+"},
            ],
            [{"text": "🚫 Không muốn nói", "callback_data": "profile:age:none"}],
            [{"text": "◀️ Quay lại Profile", "callback_data": "profile:view"}],
        ]
    }


def notification_keyboard(
    profile: UserProfile,
) -> dict[str, list[list[dict[str, str]]]]:
    briefing_status = "✅ Bật" if profile.briefing_enabled else "🔕 Tắt"
    reminder_status = "✅ Bật" if profile.reminder_enabled else "🔕 Tắt"
    return {
        "inline_keyboard": [
            [
                {
                    "text": f"🌅 Daily Briefing: {briefing_status}",
                    "callback_data": "profile:toggle:briefing",
                }
            ],
            [
                {
                    "text": f"🕖 Giờ briefing: {_fmt_time(profile.briefing_time)}",
                    "callback_data": "profile:time_menu:briefing",
                }
            ],
            [
                {
                    "text": f"⏰ Nhắc định kỳ: {reminder_status}",
                    "callback_data": "profile:toggle:reminder",
                }
            ],
            [
                {
                    "text": f"🕘 Giờ nhắc: {_fmt_time(profile.reminder_time)}",
                    "callback_data": "profile:time_menu:reminder",
                }
            ],
            [{"text": "◀️ Quay lại Profile", "callback_data": "profile:view"}],
        ]
    }


def time_keyboard(kind: str) -> dict[str, list[list[dict[str, str]]]]:
    return {
        "inline_keyboard": [
            [
                {
                    "text": _fmt_time(preset),
                    "callback_data": f"profile:time:{kind}:{_fmt_time(preset)}",
                }
                for preset in TIME_PRESETS[:2]
            ],
            [
                {
                    "text": _fmt_time(preset),
                    "callback_data": f"profile:time:{kind}:{_fmt_time(preset)}",
                }
                for preset in TIME_PRESETS[2:]
            ],
            [{"text": "✏️ Tự nhập", "callback_data": f"profile:custom_time:{kind}"}],
            [{"text": "◀️ Cài thông báo", "callback_data": "profile:notifications"}],
        ]
    }


async def get_profile_or_default(
    db: AsyncSession, user: User | ProfileUserSnapshot
) -> tuple[UserProfile, bool, str | None]:
    """Return the saved profile when available, otherwise safe defaults.

    The Profile screen is a read path. It should not fail the whole menu just
    because the optional profile overlay cannot be read (for example while a
    migration is being rolled out). Editable actions still use
    ``get_or_create_profile`` below.
    """
    try:
        profile = (
            await db.execute(select(UserProfile).where(UserProfile.user_id == user.id))
        ).scalar_one_or_none()
    except SQLAlchemyError as exc:
        notice = (
            PROFILE_SCHEMA_NOTICE
            if _looks_like_missing_profile_table(exc)
            else PROFILE_DEGRADED_NOTICE
        )
        logger.exception(
            "profile lookup failed; rendering degraded profile; schema_hint=%s",
            notice == PROFILE_SCHEMA_NOTICE,
        )
        await db.rollback()
        return _default_profile(user), False, notice

    if profile is not None:
        return profile, True, None
    return _default_profile(user), True, None


async def get_or_create_profile(db: AsyncSession, user_id) -> UserProfile:
    profile = (
        await db.execute(select(UserProfile).where(UserProfile.user_id == user_id))
    ).scalar_one_or_none()
    if profile is not None:
        return profile
    profile = UserProfile(user_id=user_id)
    db.add(profile)
    await db.flush()
    return profile


async def handle_profile_view(
    db: AsyncSession,
    chat_id: int,
    user: User,
    *,
    message_id: int | None = None,
) -> None:
    user_snapshot = _snapshot_user(user)
    profile, profile_editable, notice = await get_profile_or_default(db, user_snapshot)
    if profile_editable:
        try:
            stats = await ProfileStatsAggregator().aggregate(db, user_snapshot.id)
        except SQLAlchemyError:
            logger.exception("profile stats aggregation failed; rendering fallback stats")
            await db.rollback()
            stats = _fallback_stats()
            notice = PROFILE_DEGRADED_NOTICE
        except Exception:
            logger.exception("profile stats aggregation failed; rendering fallback stats")
            stats = _fallback_stats()
            notice = PROFILE_DEGRADED_NOTICE
    else:
        stats = _fallback_stats()
        notice = notice or PROFILE_DEGRADED_NOTICE
    text = render_profile(profile, user_snapshot, stats, notice=notice)
    if message_id is None:
        await send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="Markdown",
            reply_markup=profile_keyboard(editable=profile_editable),
        )
        return
    await edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=text,
        parse_mode="Markdown",
        reply_markup=profile_keyboard(editable=profile_editable),
    )


async def handle_profile_callback(
    db: AsyncSession,
    callback_query: dict[str, Any],
) -> bool:
    data = callback_query.get("data") or ""
    if not data.startswith("profile:"):
        return False

    callback_id = callback_query["id"]
    message = callback_query.get("message") or {}
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")
    telegram_id = (callback_query.get("from") or {}).get("id")
    user = await _get_user_by_telegram_id(db, telegram_id)
    if user is None:
        await answer_callback(
            callback_id,
            "Gõ /start để mình nhận ra bạn nhé 🌱",
            show_alert=True,
        )
        return True

    profile = await get_or_create_profile(db, user.id)
    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    await answer_callback(callback_id)

    if action == "view":
        await wizard_service.clear(db, user.id)
        await handle_profile_view(db, chat_id, user, message_id=message_id)
        return True

    if action == "edit_name":
        await wizard_service.start_flow(db, user.id, FLOW_PROFILE, STEP_DISPLAY_NAME)
        await send_message(
            chat_id=chat_id,
            text="📝 Tên mới của bạn?\n\nGõ /cancel nếu muốn bỏ qua.",
        )
        return True

    if action == "edit_age":
        await edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="🎂 Bạn thuộc nhóm tuổi nào?",
            reply_markup=age_keyboard(),
        )
        return True

    if action == "age" and len(parts) >= 3:
        value = None if parts[2] == "none" else parts[2]
        if value is not None and value not in AGE_RANGES:
            await answer_callback(callback_id, "Nhóm tuổi không hợp lệ.", show_alert=True)
            return True
        profile.age_range = value
        await db.flush()
        await send_message(chat_id=chat_id, text=_age_confirm_text(value))
        await handle_profile_view(db, chat_id, user, message_id=message_id)
        return True

    if action == "notifications":
        await _render_notifications(chat_id, message_id, profile)
        return True

    if action == "toggle" and len(parts) >= 3:
        kind = parts[2]
        if kind == "briefing":
            profile.briefing_enabled = not profile.briefing_enabled
            user.briefing_enabled = profile.briefing_enabled
        elif kind == "reminder":
            profile.reminder_enabled = not profile.reminder_enabled
        else:
            return True
        await db.flush()
        await _render_notifications(chat_id, message_id, profile)
        return True

    if action == "time_menu" and len(parts) >= 3:
        kind = parts[2]
        await edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=_time_menu_text(kind),
            reply_markup=time_keyboard(kind),
        )
        return True

    if action == "time" and len(parts) >= 4:
        kind = parts[2]
        # The preset value is HH:MM, so a plain split(":") turns
        # ``profile:time:briefing:08:00`` into [.., "08", "00"].
        # Re-join the tail to keep preset buttons from being parsed as
        # invalid and leaving the user with only a dismissed spinner.
        raw_time = ":".join(parts[3:])
        parsed = parse_hhmm(raw_time)
        if parsed is None:
            await answer_callback(callback_id, "Giờ không hợp lệ.", show_alert=True)
            return True
        await _set_notification_time(db, user, profile, kind, parsed)
        await _render_notifications(chat_id, message_id, profile)
        return True

    if action == "custom_time" and len(parts) >= 3:
        kind = parts[2]
        await wizard_service.start_flow(
            db,
            user.id,
            FLOW_PROFILE,
            STEP_NOTIFICATION_TIME,
            {"kind": kind, "message_id": message_id},
        )
        await send_message(
            chat_id=chat_id,
            text="✏️ Nhập giờ theo format HH:MM (00:00 - 23:59).\n\nGõ /cancel nếu muốn bỏ qua.",
        )
        return True

    return True


async def handle_profile_text_input(
    db: AsyncSession,
    message: dict[str, Any],
) -> bool:
    text = message.get("text", "")
    chat_id = message["chat"]["id"]
    telegram_id = (message.get("from") or {}).get("id")
    user = await _get_user_by_telegram_id(db, telegram_id)
    if user is None or (user.wizard_state or {}).get("flow") != FLOW_PROFILE:
        return False

    state = user.wizard_state or {}
    step = state.get("step")
    profile = await get_or_create_profile(db, user.id)

    if text.strip().lower() in {"/cancel", "/huy"}:
        await wizard_service.clear(db, user.id)
        await send_message(chat_id=chat_id, text="Đã hủy chỉnh sửa profile nhé.")
        await handle_profile_view(db, chat_id, user)
        return True

    if step == STEP_DISPLAY_NAME:
        name, error = sanitize_display_name(text)
        if error:
            await send_message(chat_id=chat_id, text=error)
            return True
        profile.display_name = name
        user.display_name = name
        await wizard_service.clear(db, user.id)
        await db.flush()
        await send_message(chat_id=chat_id, text=f"✅ Đã đổi tên hiển thị thành {name}.")
        await handle_profile_view(db, chat_id, user)
        return True

    if step == STEP_NOTIFICATION_TIME:
        parsed = parse_hhmm(text.strip())
        if parsed is None:
            await send_message(
                chat_id=chat_id,
                text="Giờ không hợp lệ. Format: HH:MM (00:00 - 23:59)",
            )
            return True
        kind = ((state.get("draft") or {}).get("kind") or "").strip()
        await _set_notification_time(db, user, profile, kind, parsed)
        await wizard_service.clear(db, user.id)
        await db.flush()
        await send_message(chat_id=chat_id, text=f"✅ Đã cập nhật giờ thành {_fmt_time(parsed)}.")
        await handle_profile_view(db, chat_id, user)
        return True

    return False


def render_profile(
    profile: UserProfile,
    user: User,
    stats: dict[str, Any],
    *,
    notice: str | None = None,
) -> str:
    level = stats["wealth_level"]
    progress = stats["wealth_progress"]
    name = _display_name(profile, user)
    net_worth = Decimal(stats.get("net_worth") or 0)

    lines = [
        f"👤 *Profile của {name}* {level['icon']} *{level['name_vn']}*",
        f"_{level['description']}_",
        "",
        "*Thông tin cá nhân*",
        f"• Tên hiển thị: *{name}*",
        f"• Nhóm tuổi: *{profile.age_range or 'Chưa chia sẻ'}*",
        f"• Briefing: *{'Bật' if profile.briefing_enabled else 'Tắt'}* lúc *{_fmt_time(profile.briefing_time)}*",
        f"• Nhắc định kỳ: *{'Bật' if profile.reminder_enabled else 'Tắt'}* lúc *{_fmt_time(profile.reminder_time)}*",
        "",
        "*Tổng quan*",
        f"• Tuổi tài khoản: *{stats['account_age_days']} ngày*",
        f"• Tổng tài sản: *{format_money_short(float(net_worth))}*",
        _format_wealth_journey(progress),
    ]

    change = stats.get("net_worth_change_pct")
    if change is not None:
        sign = "+" if change >= 0 else ""
        lines.append(f"• Thay đổi tài sản: *{sign}{change:.1f}%*")

    if notice:
        lines.extend(["", notice])

    lines.extend([
        "",
        "*Hoạt động tự động ghi nhận*",
        f"• Loại tài sản: *{stats['asset_types_count']}/6*",
        f"• Giao dịch tháng này: *{stats['transaction_count_this_month']}*",
        f"• Tổng giao dịch: *{stats['transaction_count_total']}*",
        (
            f"• Mục tiêu: *{stats['goals_active']} đang chạy* · "
            f"*{stats['goals_completed']} hoàn tất*"
        ),
        f"• Chuỗi hoạt động: *{stats['current_streak']} ngày* 🔥",
        f"• Briefing đã đọc: *{stats['briefing_read_count']}*",
        "",
        (
            "_Profile này được tự động tổng hợp từ dữ liệu bạn đã dùng "
            "— không cần điền form._"
        ),
    ])
    return "\n".join(lines)


def sanitize_display_name(text: str) -> tuple[str | None, str | None]:
    name = _CONTROL_CHARS_RE.sub("", text or "").strip()
    if name.startswith("@"):
        name = name[1:].strip()
    if not name:
        return None, "Tên không được trống."
    if len(name) > 50:
        return None, "Tên dài quá! Tối đa 50 ký tự nhé."
    return name, None


def parse_hhmm(value: str) -> time | None:
    match = _TIME_RE.match((value or "").strip())
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return time(hour, minute)


async def _get_user_by_telegram_id(
    db: AsyncSession,
    telegram_id: int | None,
) -> User | None:
    if telegram_id is None:
        return None
    return (
        await db.execute(select(User).where(User.telegram_id == telegram_id))
    ).scalar_one_or_none()


async def _render_notifications(
    chat_id: int,
    message_id: int | None,
    profile: UserProfile,
) -> None:
    text = (
        "🔔 *Cài thông báo*\n\n"
        f"• Daily Briefing: *{'✅ Bật' if profile.briefing_enabled else '🔕 Tắt'}*\n"
        f"• Giờ briefing: *{_fmt_time(profile.briefing_time)}*\n"
        f"• Nhắc định kỳ: *{'✅ Bật' if profile.reminder_enabled else '🔕 Tắt'}*\n"
        f"• Giờ nhắc: *{_fmt_time(profile.reminder_time)}*"
    )
    if message_id is None:
        await send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=notification_keyboard(profile),
        )
        return
    await edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=text,
        reply_markup=notification_keyboard(profile),
    )


async def _set_notification_time(
    db: AsyncSession,
    user: User,
    profile: UserProfile,
    kind: str,
    value: time,
) -> None:
    if kind == "briefing":
        profile.briefing_time = value
        user.briefing_time = value
    elif kind == "reminder":
        profile.reminder_time = value
    await db.flush()


def _looks_like_missing_profile_table(exc: SQLAlchemyError) -> bool:
    text = str(exc).lower()
    return "user_profiles" in text and (
        "does not exist" in text
        or "undefinedtable" in text
        or "missing" in text
        or "no such table" in text
    )


def _snapshot_user(user: User) -> ProfileUserSnapshot:
    return ProfileUserSnapshot(
        id=user.id,
        display_name=user.display_name,
        telegram_handle=getattr(user, "telegram_handle", None),
        briefing_enabled=bool(getattr(user, "briefing_enabled", True)),
        briefing_time=getattr(user, "briefing_time", None),
    )


def _default_profile(user: User | ProfileUserSnapshot) -> UserProfile:
    profile = UserProfile(user_id=user.id)
    profile.display_name = getattr(user, "display_name", None)
    profile.age_range = None
    profile.briefing_enabled = bool(getattr(user, "briefing_enabled", True))
    profile.briefing_time = getattr(user, "briefing_time", None) or time(7, 0)
    profile.reminder_enabled = True
    profile.reminder_time = time(9, 0)
    return profile


def _fallback_stats() -> dict[str, Any]:
    mapper = WealthLevelMapper()
    net_worth = Decimal("0")
    return {
        "account_age_days": 0,
        "net_worth": net_worth,
        "wealth_level": mapper.get_level(net_worth),
        "wealth_progress": mapper.get_progress_to_next(net_worth),
        "asset_types_count": 0,
        "transaction_count_total": 0,
        "transaction_count_this_month": 0,
        "goals_active": 0,
        "goals_completed": 0,
        "briefing_read_count": 0,
        "current_streak": 1,
        "net_worth_change_pct": None,
    }


def _display_name(profile: UserProfile, user: User | ProfileUserSnapshot) -> str:
    for value in (
        profile.display_name,
        user.display_name,
        getattr(user, "telegram_handle", None),
    ):
        value = (value or "").strip()
        if value:
            return value
    return "Bạn"


def _format_wealth_journey(progress: dict[str, Any]) -> str:
    if progress.get("at_top"):
        return "• Hành trình tài sản: *đã đạt level cao nhất* 🏆"
    pct = int(progress.get("progress_pct") or 0)
    amount = Decimal(progress.get("amount_to_next") or 0)
    next_name = progress.get("next_level_name") or "level tiếp theo"
    bar = make_progress_bar(pct, 100, width=8)
    return (
        f"• Hành trình tài sản: `{bar}` → *{next_name}* "
        f"(còn {format_money_short(float(amount))})"
    )


def _fmt_time(value: time | None) -> str:
    return (value or time(7, 0)).strftime("%H:%M")


def _age_confirm_text(value: str | None) -> str:
    if value is None:
        return "✅ Đã lưu: không chia sẻ nhóm tuổi."
    return f"✅ Đã cập nhật nhóm tuổi: {value}."


def _time_menu_text(kind: str) -> str:
    label = "briefing" if kind == "briefing" else "nhắc định kỳ"
    return f"🕒 Chọn giờ {label}:"


__all__ = [
    "FLOW_PROFILE",
    "STEP_DISPLAY_NAME",
    "PROFILE_DEGRADED_NOTICE",
    "PROFILE_SCHEMA_NOTICE",
    "ProfileUserSnapshot",
    "STEP_NOTIFICATION_TIME",
    "age_keyboard",
    "get_or_create_profile",
    "get_profile_or_default",
    "handle_profile_callback",
    "handle_profile_text_input",
    "handle_profile_view",
    "notification_keyboard",
    "parse_hhmm",
    "profile_keyboard",
    "render_profile",
    "sanitize_display_name",
    "time_keyboard",
]
