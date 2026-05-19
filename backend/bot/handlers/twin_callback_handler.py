"""Callback handlers for the Twin habit loop (Phase 4.3 Story 3.1-3.6).

These wire the inline-keyboard buttons that the on-demand recompute
notification (``twin:causality`` / ``twin:action``) and the action
suggestion card (``action_suggestion:dismiss:*`` / ``twin:action_done:*``)
present to the user. Without these the buttons were dead ends — Telegram
showed the spinner until the worker's generic ``answerCallbackQuery``
fallback fired, with no follow-up message.

Layer: handler — formats Telegram payloads, calls services, flushes only.
Worker owns the commit boundary.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from backend import analytics
from backend.models.event import Event
from backend.services.dashboard_service import get_user_by_telegram_id
from backend.services.telegram_service import answer_callback, send_message
from backend.twin.services import (
    action_suggestion_service,
    causality_service,
    return_tease_service,
)

logger = logging.getLogger(__name__)

_CAUSALITY_PREFIX = "twin:causality"
_ACTION_PREFIX = "twin:action"
_ACTION_DONE_PREFIX = "twin:action_done:"
_DISMISS_PREFIX = "action_suggestion:dismiss:"


def _to_action_button() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "🎯 Việc nên làm tiếp →", "callback_data": _ACTION_PREFIX}]
        ]
    }


def _action_card_keyboard(suggestion_type: str) -> dict:
    """Two-button card for the action suggestion. Both buttons are
    callbacks — we deliberately avoid Telegram ``url`` buttons here
    because the seed library uses ``betien://`` deep links that the
    Bot API rejects (only http/https/tg:// allowed).
    """
    return {
        "inline_keyboard": [
            [
                {
                    "text": "✅ Mình làm rồi",
                    "callback_data": f"{_ACTION_DONE_PREFIX}{suggestion_type}",
                },
                {
                    "text": "🤔 Để tôi nghĩ thêm",
                    "callback_data": f"{_DISMISS_PREFIX}{suggestion_type}",
                },
            ]
        ]
    }


async def _has_active_goal(db: AsyncSession, user_id) -> bool:
    from backend.services import goal_service

    goals = await goal_service.list_goals(db, user_id, active_only=True)
    return bool(goals)


async def handle_twin_callback(db: AsyncSession, callback_query: dict) -> bool:
    """Route ``twin:causality``, ``twin:action`` and ``twin:action_done:*``."""
    data = callback_query.get("data") or ""
    if not (
        data == _CAUSALITY_PREFIX
        or data == _ACTION_PREFIX
        or data.startswith(_ACTION_DONE_PREFIX)
    ):
        return False

    callback_id = callback_query["id"]
    chat_id = (callback_query.get("message") or {}).get("chat", {}).get("id")
    telegram_id = (callback_query.get("from") or {}).get("id")

    # Acknowledge immediately so the user's spinner clears in <100ms even
    # if the service work below takes a moment.
    await answer_callback(callback_id)

    if chat_id is None or telegram_id is None:
        return True

    user = await get_user_by_telegram_id(db, telegram_id)
    if user is None:
        # Nothing to attribute the action to — silent ack.
        return True

    if data == _CAUSALITY_PREFIX:
        await _send_causality(db, chat_id, user)
        return True

    if data == _ACTION_PREFIX:
        await _send_action_suggestion(db, chat_id, user)
        return True

    if data.startswith(_ACTION_DONE_PREFIX):
        suggestion_type = data[len(_ACTION_DONE_PREFIX):] or "unknown"
        await _send_action_done(db, chat_id, user, suggestion_type)
        return True

    return True


async def handle_action_suggestion_callback(
    db: AsyncSession, callback_query: dict
) -> bool:
    """Route ``action_suggestion:dismiss:<type>``. The 30-day suppression
    that ``action_suggestion_service`` enforces reads the events written
    here, so the dismiss is what drives "stop suggesting this for a while".
    """
    data = callback_query.get("data") or ""
    if not data.startswith(_DISMISS_PREFIX):
        return False

    callback_id = callback_query["id"]
    chat_id = (callback_query.get("message") or {}).get("chat", {}).get("id")
    telegram_id = (callback_query.get("from") or {}).get("id")
    await answer_callback(callback_id)

    suggestion_type = data[len(_DISMISS_PREFIX):] or "unknown"

    if telegram_id is None:
        return True
    user = await get_user_by_telegram_id(db, telegram_id)
    if user is None:
        return True

    db.add(
        Event(
            user_id=user.id,
            event_type="action_suggestion.dismissed",
            properties={"suggestion_type": suggestion_type},
        )
    )
    await db.flush()

    analytics.track(
        analytics.EventType.BUTTON_TAPPED,
        user_id=user.id,
        properties={"button": "action_suggestion:dismiss", "suggestion_type": suggestion_type},
    )

    if chat_id is not None:
        await send_message(
            chat_id,
            "Để Bé Tiền nhắc nhẹ sau vài ngày khi anh đỡ bận nhé 💚",
            parse_mode=None,
        )
    return True


async def _send_causality(db: AsyncSession, chat_id: int, user) -> None:
    try:
        breakdown = await causality_service.attribute_delta(db, user.id)
    except Exception:
        logger.exception("twin:causality failed user=%s", user.id)
        await send_message(
            chat_id,
            "Bé Tiền chưa tổng hợp được thay đổi tuần này. Anh quay lại sau ít phút giúp Bé nhé 💚",
            parse_mode=None,
        )
        return

    text = breakdown.text or "Twin của anh ổn định tuần này."
    # Only chain to action suggestion when there's meaningful delta to react
    # to — pointing a user with a flat week toward "what to do next" feels
    # tacked on.
    reply_markup = _to_action_button() if breakdown.show_breakdown else None
    await send_message(chat_id, text, parse_mode=None, reply_markup=reply_markup)

    analytics.track(
        analytics.EventType.BUTTON_TAPPED,
        user_id=user.id,
        properties={"button": "twin:causality", "direction": breakdown.direction},
    )


async def _send_action_suggestion(db: AsyncSession, chat_id: int, user) -> None:
    try:
        breakdown = await causality_service.attribute_delta(db, user.id)
        delta_pct = float(breakdown.delta_pct)
    except Exception:
        logger.exception("twin:action causality lookup failed user=%s", user.id)
        delta_pct = 0.0

    has_goal = await _has_active_goal(db, user.id)
    segment = getattr(user, "wealth_level", None) or "mass_affluent"

    try:
        suggestion = await action_suggestion_service.suggest_action(
            db,
            user.id,
            state_segment=segment,
            delta_pct=delta_pct,
            has_goal=has_goal,
        )
    except Exception:
        logger.exception("twin:action suggest failed user=%s", user.id)
        await send_message(
            chat_id,
            "Bé Tiền chưa gợi ý được việc nên làm ngay. Anh thử lại sau nhé 💚",
            parse_mode=None,
        )
        return

    try:
        await action_suggestion_service.log_action_event(
            db, user.id, "action_suggestion.shown", suggestion
        )
    except Exception:
        # Never block the UX on a logging hiccup.
        logger.warning("action_suggestion.shown log failed", exc_info=True)

    text = action_suggestion_service.render_action_card(suggestion)
    await send_message(
        chat_id,
        text,
        parse_mode=None,
        reply_markup=_action_card_keyboard(suggestion.type),
    )

    analytics.track(
        analytics.EventType.BUTTON_TAPPED,
        user_id=user.id,
        properties={
            "button": "twin:action",
            "suggestion_type": suggestion.type,
            "has_goal": has_goal,
        },
    )


async def _send_action_done(
    db: AsyncSession, chat_id: int, user, suggestion_type: str
) -> None:
    try:
        tease = await return_tease_service.record_action_completed(
            db, user.id, action_title=suggestion_type
        )
    except Exception:
        logger.exception("twin:action_done record failed user=%s", user.id)
        await send_message(
            chat_id,
            "Bé Tiền đã ghi nhận. Cảm ơn anh 💚",
            parse_mode=None,
        )
        return

    body = tease.confirmation
    if tease.tease:
        body = f"{body}\n\n{tease.tease}"
    await send_message(chat_id, body, parse_mode=None)

    analytics.track(
        analytics.EventType.BUTTON_TAPPED,
        user_id=user.id,
        properties={"button": "twin:action_done", "suggestion_type": suggestion_type},
    )
