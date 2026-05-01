"""Phase 3.5 entry point — route free-form text through the intent pipeline.

Called from ``backend.bot.handlers.message.handle_text_message`` after
the existing fast paths (report, asset list) have had a chance to fire.
Owns the analytics events for the intent layer so all observation lives
in one place.

The pipeline + dispatcher are module-level singletons so the YAML
patterns load exactly once per worker process.
"""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from backend import analytics
from backend.intent.classifier.pipeline import IntentPipeline
from backend.intent.dispatcher import IntentDispatcher
from backend.intent.intents import IntentType
from backend.models.user import User
from backend.services.telegram_service import send_message

logger = logging.getLogger(__name__)


# Eagerly construct so the YAML patterns load once at import time
# rather than once per request. Tests can swap them via
# ``set_pipeline`` / ``set_dispatcher`` if they need an alternate
# config (e.g. injecting an LLM stub for Epic 2 work).
_pipeline = IntentPipeline()
_dispatcher = IntentDispatcher()


# Analytics event names — kept as module constants so tests can assert
# against the same strings the producer uses.
EVENT_INTENT_CLASSIFIED = "intent_classified"
EVENT_INTENT_HANDLER_EXECUTED = "intent_handler_executed"
EVENT_INTENT_UNCLEAR = "intent_unclear"


def set_pipeline(pipeline: IntentPipeline) -> None:
    """Test hook: replace the module-level pipeline."""
    global _pipeline
    _pipeline = pipeline


def set_dispatcher(dispatcher: IntentDispatcher) -> None:
    """Test hook: replace the module-level dispatcher."""
    global _dispatcher
    _dispatcher = dispatcher


async def handle_free_form_text(
    db: AsyncSession,
    *,
    chat_id: int,
    user: User,
    text: str,
) -> bool:
    """Route a free-form message through intent classification.

    Returns True when something was sent to the user. The caller
    should treat True as "consumed — do not run further fallbacks".
    """
    if not text or not text.strip():
        return False

    try:
        result = await _pipeline.classify(text)
    except Exception:
        logger.exception("Intent pipeline crashed")
        return False

    analytics.track(
        EVENT_INTENT_CLASSIFIED,
        user_id=user.id,
        properties={
            "intent": result.intent.value,
            "confidence": round(result.confidence, 3),
            "classifier": result.classifier_used,
        },
    )

    response = await _dispatcher.dispatch(result, user, db)

    sent = await send_message(chat_id, response)
    delivered = sent is not None

    if result.intent in (IntentType.UNCLEAR, IntentType.OUT_OF_SCOPE):
        analytics.track(
            EVENT_INTENT_UNCLEAR,
            user_id=user.id,
            properties={
                "intent": result.intent.value,
                "delivered": delivered,
            },
        )
    else:
        analytics.track(
            EVENT_INTENT_HANDLER_EXECUTED,
            user_id=user.id,
            properties={
                "intent": result.intent.value,
                "confidence": round(result.confidence, 3),
                "delivered": delivered,
            },
        )

    return True
