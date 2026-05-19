"""Manual resend command for the enriched morning briefing."""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from backend import analytics
from backend.briefing.morning_briefing import render_enriched_morning_briefing
from backend.bot.keyboards.briefing_keyboard import briefing_actions_keyboard
from backend.bot.utils.emoji_animation import message_kwargs_for_animation
from backend.models.user import User
from backend.ports.notifier import get_notifier
from backend.services.telegram_service import send_message

logger = logging.getLogger(__name__)


async def send_morning_briefing_now(
    db: AsyncSession,
    *,
    chat_id: int,
    user: User | None,
) -> bool:
    """Render and send the latest briefing on demand.

    Manual sends intentionally do not write ``MORNING_BRIEFING_SENT`` so they
    cannot suppress the scheduled daily delivery when a user asks before their
    configured briefing time.
    """
    if user is None:
        await send_message(
            chat_id,
            "🌅 Mình chưa tìm thấy tài khoản của bạn. Gõ /start trước nhé.",
            parse_mode="HTML",
        )
        return False

    result = await render_enriched_morning_briefing(db, user)
    response = await get_notifier().send_message(
        chat_id=chat_id,
        text=result.text,
        parse_mode=None,
        reply_markup=briefing_actions_keyboard(
            include_twin=bool(result.sections.get("twin"))
        ),
        **message_kwargs_for_animation(result.text, "briefing"),
    )
    if response is None:
        await send_message(
            chat_id,
            "⚠️ Mình chưa gửi lại báo cáo sáng được. Bạn thử lại sau ít phút nhé.",
            parse_mode="HTML",
        )
        return False

    await analytics.atrack(
        "morning_briefing_requested",
        user_id=user.id,
        properties={
            "level": result.level.value,
            "is_empty_state": result.is_empty_state,
            "char_count": result.char_count,
            "is_stale": result.is_stale,
            "render_ms": result.render_ms,
        },
    )
    logger.info("Manual morning briefing sent to user %s", user.id)
    return True
