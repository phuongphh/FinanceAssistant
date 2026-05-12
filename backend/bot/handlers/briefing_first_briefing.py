"""First-briefing "Bé Tiền đang nói gì?" explainer (Phase 4.1, A.8).

Tiny handler — answers a callback by sending the explanation panel
(content/onboarding/first_briefing.yaml § explanation). Kept in its
own file so the explainer copy isn't tangled with the existing
briefing callback router.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from backend import analytics
from backend.services.briefing import first_briefing_service
from backend.services.telegram_service import answer_callback, send_message

logger = logging.getLogger(__name__)


async def handle_first_briefing_callback(
    db: AsyncSession, callback_query: dict
) -> bool:
    data = callback_query.get("data") or ""
    if not data.startswith("first_briefing:"):
        return False

    callback_id = callback_query["id"]
    chat_id = (callback_query.get("message") or {}).get("chat", {}).get("id")
    from_user = callback_query.get("from") or {}
    telegram_id = from_user.get("id")

    if chat_id is None:
        await answer_callback(callback_id)
        return True

    action = data.split(":", 1)[1] if ":" in data else ""

    if action == "explain":
        await answer_callback(callback_id)
        await send_message(
            chat_id,
            first_briefing_service.explanation_text(),
            parse_mode="HTML",
        )
        if telegram_id is not None:
            from backend.services.dashboard_service import (
                get_user_by_telegram_id,
            )

            user = await get_user_by_telegram_id(db, telegram_id)
            if user:
                analytics.track(
                    "first_briefing_explain_tapped",
                    user_id=user.id,
                )
        return True

    await answer_callback(callback_id)
    return True
