from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.formatters.money import format_money_short
from backend.bot.formatters.progress_bar import make_progress_bar
from backend.models.user import User
from backend.profile.models.user_profile import UserProfile
from backend.profile.services.stats_aggregator import ProfileStatsAggregator
from backend.services.telegram_service import edit_message_text, send_message


def profile_keyboard() -> dict[str, list[list[dict[str, str]]]]:
    return {
        "inline_keyboard": [
            [
                {"text": "📝 Đổi tên", "callback_data": "profile:edit_name"},
                {"text": "🎂 Đổi tuổi", "callback_data": "profile:edit_age"},
            ],
            [{"text": "🔔 Cài thông báo", "callback_data": "profile:notifications"}],
            [{"text": "◀️ Quay lại", "callback_data": "menu:main"}],
        ]
    }


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
    profile = await get_or_create_profile(db, user.id)
    stats = await ProfileStatsAggregator().aggregate(db, user.id)
    text = render_profile(profile, user, stats)
    if message_id is None:
        await send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="Markdown",
            reply_markup=profile_keyboard(),
        )
        return
    await edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=text,
        parse_mode="Markdown",
        reply_markup=profile_keyboard(),
    )


def render_profile(profile: UserProfile, user: User, stats: dict[str, Any]) -> str:
    level = stats["wealth_level"]
    progress = stats["wealth_progress"]
    name = _display_name(profile, user)
    net_worth = Decimal(stats.get("net_worth") or 0)

    lines = [
        f"👤 *Profile của {name}* {level['icon']} *{level['name_vn']}*",
        f"_{level['description']}_",
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


def _display_name(profile: UserProfile, user: User) -> str:
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


__all__ = [
    "get_or_create_profile",
    "handle_profile_view",
    "profile_keyboard",
    "render_profile",
]
