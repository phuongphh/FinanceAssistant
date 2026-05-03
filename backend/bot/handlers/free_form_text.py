"""Phase 3.5 entry point — route free-form text through the intent pipeline.

Called from ``backend.bot.handlers.message.handle_text_message`` after
the existing fast paths (report, asset list) have had a chance to fire.
Owns the analytics events for the intent layer so all observation lives
in one place.

Pending-state precedence:
  1. If the user has an active ``intent_pending_action`` (they typed a
     write at medium confidence and we asked for confirmation), the
     callback handler in ``callbacks.py`` resolves it. Plain-text
     messages while pending fall through to a "still waiting" reminder.
  2. If the user has an active ``intent_awaiting_clarify`` state, the
     incoming message is treated as the clarification and re-classified
     against the original intent.
  3. Otherwise, normal classification.

Pipeline + dispatcher are module-level singletons so the YAML
patterns load exactly once per worker process.
"""
from __future__ import annotations

import logging
import time

from sqlalchemy.ext.asyncio import AsyncSession

from backend import analytics
from backend.intent import pending_action
from backend.intent.classifier.llm_based import LLMClassifier
from backend.intent.classifier.pipeline import IntentPipeline
from backend.intent.classifier.rule_based import RuleBasedClassifier
from backend.intent.dispatcher import (
    DispatchOutcome,
    IntentDispatcher,
    OUTCOME_CLARIFY_SENT,
    OUTCOME_CONFIRM_SENT,
    OUTCOME_OUT_OF_SCOPE,
    OUTCOME_UNCLEAR,
)
from backend.intent.intents import IntentResult, IntentType
from backend.models.user import User
from backend.services.telegram_service import send_message

logger = logging.getLogger(__name__)


# Eagerly construct so the YAML patterns load once at import time
# rather than once per request. Tests can swap them via
# ``set_pipeline`` / ``set_dispatcher``.
_pipeline = IntentPipeline(
    rule_classifier=RuleBasedClassifier(),
    llm_classifier=LLMClassifier(),
)
_dispatcher = IntentDispatcher()


# Analytics event names — kept as module constants so tests can assert
# against the same strings the producer uses.
EVENT_INTENT_CLASSIFIED = "intent_classified"
EVENT_INTENT_HANDLER_EXECUTED = "intent_handler_executed"
EVENT_INTENT_UNCLEAR = "intent_unclear"
EVENT_INTENT_CLARIFY_SENT = "intent_clarification_sent"
EVENT_INTENT_CLARIFY_RESOLVED = "intent_clarification_resolved"
EVENT_INTENT_CONFIRM_SENT = "intent_confirm_sent"
EVENT_LLM_CLASSIFIER_CALL = "llm_classifier_call"


def set_pipeline(pipeline: IntentPipeline) -> None:
    """Test hook: replace the module-level pipeline."""
    global _pipeline
    _pipeline = pipeline


def set_dispatcher(dispatcher: IntentDispatcher) -> None:
    """Test hook: replace the module-level dispatcher."""
    global _dispatcher
    _dispatcher = dispatcher


def _build_inline_keyboard(
    labels: list[str] | None,
    *,
    intent: IntentType | None = None,
    follow_ups: list = None,
    is_executed: bool = False,
) -> dict | None:
    """Telegram inline keyboard payload.

    For executed handlers we send ``followup:<encoded>`` callbacks via
    ``follow_up.build_inline_keyboard`` so a tap re-runs a related
    intent. For clarifications the callback is ``intent_clarify:<idx>``.
    Empty / None labels → no keyboard.
    """
    if is_executed and follow_ups:
        from backend.intent.follow_up import build_inline_keyboard
        return build_inline_keyboard(follow_ups)
    if not labels:
        return None
    return {
        "inline_keyboard": [
            [
                {
                    "text": label,
                    "callback_data": f"intent_clarify:{i}",
                }
            ]
            for i, label in enumerate(labels)
        ]
    }


def _build_confirm_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Đúng", "callback_data": "intent_confirm:yes"},
                {"text": "❌ Không phải", "callback_data": "intent_confirm:no"},
            ]
        ]
    }


async def _track_classification(
    user: User, result: IntentResult, latency_ms: int
) -> None:
    analytics.track(
        EVENT_INTENT_CLASSIFIED,
        user_id=user.id,
        properties={
            "intent": result.intent.value,
            "confidence": round(result.confidence, 3),
            "classifier": result.classifier_used,
            "latency_ms": latency_ms,
        },
    )

    # If the LLM ran, surface its cost to a dedicated event so the
    # admin metrics endpoint can sum it without joining the cache table.
    llm = getattr(_pipeline.llm_classifier, "last_call_stats", None)
    if (
        result.classifier_used == "llm"
        and llm is not None
        and not llm.cache_hit
    ):
        analytics.track(
            EVENT_LLM_CLASSIFIER_CALL,
            user_id=user.id,
            properties={
                "input_tokens": llm.input_tokens,
                "output_tokens": llm.output_tokens,
                "latency_ms": llm.latency_ms,
                "cost_usd": round(llm.cost_usd, 6),
                "cache_hit": False,
            },
        )


async def _track_outcome(user: User, outcome: DispatchOutcome) -> None:
    if outcome.kind == OUTCOME_CLARIFY_SENT:
        analytics.track(
            EVENT_INTENT_CLARIFY_SENT,
            user_id=user.id,
            properties={
                "original_intent": outcome.intent.value,
                "clarification_type": outcome.intent.value,
            },
        )
        return

    if outcome.kind == OUTCOME_CONFIRM_SENT:
        analytics.track(
            EVENT_INTENT_CONFIRM_SENT,
            user_id=user.id,
            properties={"intent": outcome.intent.value},
        )
        return

    if outcome.kind in (OUTCOME_UNCLEAR, OUTCOME_OUT_OF_SCOPE):
        analytics.track(
            EVENT_INTENT_UNCLEAR,
            user_id=user.id,
            properties={"intent": outcome.intent.value},
        )
        return

    analytics.track(
        EVENT_INTENT_HANDLER_EXECUTED,
        user_id=user.id,
        properties={
            "intent": outcome.intent.value,
            "confidence": round(outcome.confidence, 3),
            "outcome": outcome.kind,
        },
    )


async def _send_outcome(chat_id: int, outcome: DispatchOutcome) -> None:
    """Send the outcome text + appropriate keyboard."""
    from backend.intent.dispatcher import OUTCOME_EXECUTED
    from backend.intent import follow_up

    if outcome.kind == OUTCOME_CONFIRM_SENT:
        keyboard = _build_confirm_keyboard()
    elif outcome.kind == OUTCOME_EXECUTED and outcome.inline_keyboard_hint:
        # The dispatcher passed labels; rebuild as follow-up suggestions
        # using the same intent so the callback round-trips correctly.
        # We don't have access to the wealth level here, so re-derive
        # via follow_up's default pool (matches the labels we got).
        suggestions = follow_up.get_follow_ups(
            outcome.intent, avoid_intent=outcome.intent
        )
        # Filter to the labels the dispatcher selected — keeps the two
        # paths in sync if e.g. the dispatcher shrunk the list.
        wanted = set(outcome.inline_keyboard_hint)
        suggestions = [fu for fu in suggestions if fu.label in wanted]
        keyboard = follow_up.build_inline_keyboard(suggestions)
    else:
        keyboard = _build_inline_keyboard(outcome.inline_keyboard_hint)
    await send_message(chat_id, outcome.text, reply_markup=keyboard)


async def classify_and_dispatch(
    db: AsyncSession,
    *,
    chat_id: int,
    user: User,
    text: str,
) -> DispatchOutcome | None:
    """Run the full intent flow. Returns the outcome (or None if the
    text was empty) so callers can decide whether to fall through to
    the LLM transaction parser.

    The function:
      1. Clears expired pending state.
      2. If state is active, treats the message as a resolution.
      3. Otherwise classifies + dispatches normally.
    """
    if not text or not text.strip():
        return None

    started = time.perf_counter()
    await pending_action.clear_if_expired(db, user)
    state = pending_action.get_active(user)
    if state and state.get("flow") == pending_action.FLOW_AWAITING_CLARIFY:
        # Resolve clarification: re-classify the new text against the
        # original intent. We persist NOTHING — clearing is done after
        # dispatch so the next message starts fresh.
        await pending_action.clear(db, user)
        outcome = await _resolve_clarification(state, text, user, db)
        await _send_outcome(chat_id, outcome)
        analytics.track(
            EVENT_INTENT_CLARIFY_RESOLVED,
            user_id=user.id,
            properties={
                "original_intent": state.get("original_intent"),
                "final_intent": outcome.intent.value,
            },
        )
        return outcome

    if state and state.get("flow") == pending_action.FLOW_PENDING_ACTION:
        # Plain text while a confirmation is pending — nudge them to
        # tap a button. The callback handler resolves the actual action.
        from backend.intent import clarifier

        text_msg = clarifier.build_awaiting_response(user)
        await send_message(chat_id, text_msg, reply_markup=_build_confirm_keyboard())
        return DispatchOutcome(
            text=text_msg,
            kind=OUTCOME_CONFIRM_SENT,
            intent=IntentType(state.get("intent", IntentType.UNCLEAR.value)),
        )

    # Normal path.
    result = await _pipeline.classify(text)
    latency_ms = int((time.perf_counter() - started) * 1000)
    await _track_classification(user, result, latency_ms)

    outcome = await _dispatcher.dispatch(result, user, db)
    await _send_outcome(chat_id, outcome)
    await _track_outcome(user, outcome)
    return outcome


async def _resolve_clarification(
    state: dict,
    new_text: str,
    user: User,
    db: AsyncSession,
) -> DispatchOutcome:
    """Re-classify the user's clarification reply.

    Strategy: classify the new_text fresh; if it succeeds with decent
    confidence, dispatch that. If it doesn't, fall back to the
    original intent at HIGH confidence (treating the clarification as
    additional context).
    """
    new_result = await _pipeline.classify(new_text)
    if (
        new_result.intent != IntentType.UNCLEAR
        and new_result.confidence >= 0.5
    ):
        return await _dispatcher.dispatch(new_result, user, db)

    # Fallback — promote the original intent to high confidence and
    # carry over the original parameters merged with any new ones.
    try:
        original = IntentType(state.get("original_intent", "unclear"))
    except ValueError:
        original = IntentType.UNCLEAR
    merged_params = dict(state.get("parameters") or {})
    merged_params.update(new_result.parameters or {})
    fallback = IntentResult(
        intent=original,
        confidence=0.85,
        parameters=merged_params,
        raw_text=new_text,
        classifier_used="rule",  # treated as user-confirmed
    )
    return await _dispatcher.dispatch(fallback, user, db)


# Backwards-compat shim: the existing message.py + tests call
# ``handle_free_form_text`` and expect ``True`` on success. Keep this
# entry point so existing callers keep working — tests can use either
# this or ``classify_and_dispatch``.
async def handle_free_form_text(
    db: AsyncSession,
    *,
    chat_id: int,
    user: User,
    text: str,
) -> bool:
    outcome = await classify_and_dispatch(
        db=db, chat_id=chat_id, user=user, text=text
    )
    return outcome is not None
