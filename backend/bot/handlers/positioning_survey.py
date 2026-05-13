from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.keyboards.common import parse_callback
from backend.services import dashboard_service
from backend.services.survey import positioning_survey_service
from backend.services.telegram_service import answer_callback

logger = logging.getLogger(__name__)

CB_POSITIONING_SURVEY = "positioning_survey"


async def handle_positioning_survey_callback(
    db: AsyncSession, callback_query: dict
) -> bool:
    data = callback_query.get("data") or ""
    prefix, args = parse_callback(data)
    if prefix != CB_POSITIONING_SURVEY:
        return False

    callback_id = callback_query["id"]
    telegram_id = (callback_query.get("from") or {}).get("id")
    if telegram_id is None:
        await answer_callback(
            callback_id,
            text="Bé Tiền chưa nhận ra bạn — gõ /start giúp mình nhé.",
            show_alert=True,
        )
        return True

    user = await dashboard_service.get_user_by_telegram_id(db, telegram_id)
    if user is None:
        await answer_callback(
            callback_id,
            text="Bé Tiền chưa nhận ra bạn — gõ /start giúp mình nhé.",
            show_alert=True,
        )
        return True

    if not args:
        await answer_callback(callback_id)
        return True

    response = args[0]
    copy = positioning_survey_service.load_copy()
    try:
        inserted = await positioning_survey_service.record_response(
            db, user.id, response
        )
    except ValueError:
        logger.warning("invalid positioning survey callback: %s", data)
        await answer_callback(
            callback_id,
            text="Lựa chọn này không hợp lệ nữa — bạn thử lại giúp mình nhé.",
            show_alert=True,
        )
        return True

    await answer_callback(
        callback_id,
        text=copy.ack if inserted else copy.duplicate_ack,
        show_alert=False,
    )
    return True
