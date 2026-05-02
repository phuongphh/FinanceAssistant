"""Handle free-text Telegram messages.

Phase 3.5 routing order (after the worker has dispatched commands and
wizards):

  1. Report intent (legacy, still served by ``report_service``).
  2. Pending intent state (confirm-await / clarify-await) handled by
     ``classify_and_dispatch`` — it inspects ``user.wizard_state`` first
     and resolves any active intent flow.
  3. ``IntentPipeline.classify`` — covers ~95% of queries (rule-based
     + LLM fallback). Confident matches dispatch immediately.
  4. LLM transaction parser — fallback for "vừa chi 200k ăn trưa"
     style messages that don't match any query pattern.
  5. Dispatcher's UNCLEAR / OOS reply — final fallback so the user
     always gets a friendly message (no silent fail).
"""
from __future__ import annotations

import json
import logging
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.handlers import free_form_text as intent_layer
from backend.bot.handlers.transaction import send_transaction_confirmation
from backend.intent import pending_action
from backend.intent.dispatcher import (
    OUTCOME_CLARIFY_SENT,
    OUTCOME_CONFIRM_SENT,
    OUTCOME_OUT_OF_SCOPE,
    OUTCOME_UNCLEAR,
)
from backend.intent.intents import IntentType
from backend.schemas.expense import ExpenseCreate
from backend.services import expense_service, report_service
from backend.services.dashboard_service import get_user_by_telegram_id
from backend.services.llm_service import call_llm
from backend.services.telegram_service import send_message

logger = logging.getLogger(__name__)

_PARSE_PROMPT = """Parse chi tiêu từ text sau và trả về JSON:
"{text}"

Trả về JSON với format:
{{"amount": <số>, "merchant": "<tên hoặc mô tả ngắn>", "is_expense": <true|false>}}

Quy tắc:
- Nếu có số tiền và mô tả → is_expense: true
- Nếu là câu hỏi, tin nhắn thông thường, không phải chi tiêu → is_expense: false, amount: 0
- "k" hoặc "K" cuối số = × 1000: 50k = 50000, 150k = 150000
- merchant = nơi mua hoặc mô tả ngắn gọn nhất

Chỉ trả về JSON, không giải thích."""

_NOT_REGISTERED = "Bạn chưa đăng ký. Gửi /start để bắt đầu."

# Outcome kinds that mean "the user got their answer / a follow-up
# prompt — do NOT fall through to the LLM transaction parser".
_TERMINAL_OUTCOMES = frozenset(
    {OUTCOME_CLARIFY_SENT, OUTCOME_CONFIRM_SENT, OUTCOME_OUT_OF_SCOPE}
)


async def _send_report(
    db: AsyncSession, chat_id: int, telegram_id: int, text: str = ""
) -> None:
    """Ask the service for report text and deliver it to the user."""
    await send_message(chat_id, "⏳ Đang tổng hợp báo cáo...")
    result = await report_service.process_report_request(db, telegram_id, text)
    await send_message(chat_id, result)


async def handle_report_command(db: AsyncSession, message: dict) -> None:
    """Handle /report command — extracts Telegram data, delegates to service."""
    chat_id = message["chat"]["id"]
    telegram_id = (message.get("from") or {}).get("id", chat_id)
    await _send_report(db, chat_id, telegram_id)


async def handle_report_callback(db: AsyncSession, callback_query: dict) -> None:
    """Handle menu:report callback — extracts Telegram data, delegates to service."""
    chat_id = callback_query["message"]["chat"]["id"]
    telegram_id = (callback_query.get("from") or {}).get("id", chat_id)
    await _send_report(db, chat_id, telegram_id)


async def handle_text_message(db: AsyncSession, message: dict) -> bool:
    """Route a plain-text message through the Phase 3.5 intent pipeline,
    falling back to the LLM transaction parser, then to the unclear/OOS
    handler.

    Returns True once a reply has been sent (so the caller stops trying
    other handlers). Returns False only when the message has no text at
    all — then the caller can still answer with a generic prompt.
    """
    text = message.get("text", "").strip()
    if not text:
        return False

    chat_id = message["chat"]["id"]
    from_data = message.get("from") or {}
    telegram_id = from_data.get("id", chat_id)

    # Fast-path: report intent — service handles all orchestration.
    if report_service.is_report_query(text):
        await _send_report(db, chat_id, telegram_id, text)
        return True

    user = await get_user_by_telegram_id(db, telegram_id)
    if not user:
        await send_message(chat_id, _NOT_REGISTERED)
        return True

    # Phase 3.5 — full intent flow with confirm/clarify state handling.
    outcome = await intent_layer.classify_and_dispatch(
        db=db, chat_id=chat_id, user=user, text=text
    )

    if outcome is None:
        return False  # empty text — shouldn't happen given the early return

    # Confident execution OR terminal outcomes (clarify/confirm/OOS) — done.
    if (
        outcome.kind not in (OUTCOME_UNCLEAR,)
        and outcome.intent != IntentType.UNCLEAR
    ):
        return True
    if outcome.kind in _TERMINAL_OUTCOMES:
        return True

    # UNCLEAR — try the LLM transaction parser before giving up. The
    # dispatcher already sent the unclear reply, so we only proceed if
    # the parser returns a real transaction; if not, the unclear text
    # remains the final answer.
    parsed: dict | None = None
    try:
        raw = await call_llm(
            _PARSE_PROMPT.format(text=text),
            task_type="parse_manual",
            db=db,
            user_id=user.id,
            use_cache=False,
        )
        lines = [l for l in raw.splitlines() if not l.startswith("```")]
        parsed = json.loads("\n".join(lines))
    except Exception:
        logger.exception("LLM parse failed for text: %r", text)
        parsed = None

    if (
        parsed
        and parsed.get("is_expense")
        and float(parsed.get("amount", 0)) > 0
    ):
        expense_data = ExpenseCreate(
            amount=float(parsed["amount"]),
            merchant=parsed.get("merchant") or text,
            note=text,
            source="manual",
            expense_date=date.today(),
        )
        expense = await expense_service.create_expense(db, user.id, expense_data)
        await send_transaction_confirmation(db, expense)
        return True

    # Already sent the unclear reply via the dispatcher.
    return True


# -------------------- callback handler --------------------


async def handle_intent_callback(db: AsyncSession, callback_query: dict) -> bool:
    """Resolve an Epic 2 / Epic 3 intent callback.

    Three callback prefixes share this entry point:
      - ``intent_confirm:yes|no`` (Epic 2 — pending write action)
      - ``intent_clarify:<idx>``  (Epic 2 — disambiguation buttons)
      - ``followup:<payload>``    (Epic 3 — re-run a related intent)

    Returns True when the callback was recognised and handled. The
    worker dispatches this BEFORE the menu callback handler so menu
    callbacks aren't shadowed by the more specific intent prefix.
    """
    from backend.intent import follow_up

    data = callback_query.get("data", "")
    if not (
        data.startswith("intent_") or data.startswith(follow_up.CALLBACK_PREFIX)
    ):
        return False

    chat_id = callback_query["message"]["chat"]["id"]
    from_user = callback_query.get("from") or {}
    telegram_id = from_user.get("id", chat_id)
    user = await get_user_by_telegram_id(db, telegram_id)
    if not user:
        return True  # ignore — user gone

    state = pending_action.get_active(user)

    if data.startswith("intent_confirm:"):
        return await _handle_confirm_callback(
            db, chat_id, user, state, action=data.split(":", 1)[1]
        )

    if data.startswith("intent_clarify:"):
        return await _handle_clarify_callback(
            db, chat_id, user, state, index=data.split(":", 1)[1]
        )

    if data.startswith(follow_up.CALLBACK_PREFIX):
        return await _handle_followup_callback(db, chat_id, user, data)

    return False


async def _handle_followup_callback(
    db: AsyncSession,
    chat_id: int,
    user,
    callback_data: str,
) -> bool:
    """Resolve a ``followup:<...>`` tap by re-running the encoded intent.

    The follow-up button carries the target intent + parameters in its
    callback_data; we synthesise an ``IntentResult`` at high confidence
    and dispatch it through the normal pipeline (so personality +
    suggestions still apply).
    """
    from backend.bot.handlers import free_form_text as intent_layer
    from backend.intent import follow_up
    from backend.intent.classifier.base import IntentClassifier  # noqa: F401
    from backend.intent.intents import CLASSIFIER_RULE, IntentResult

    parsed = follow_up.parse_callback_data(callback_data)
    if parsed is None:
        await send_message(
            chat_id,
            "Câu hỏi này đã hết hạn rồi 🌱 — bạn hỏi lại nhé.",
        )
        return True

    synthesised = IntentResult(
        intent=parsed.intent,
        confidence=0.95,
        parameters=dict(parsed.parameters or {}),
        raw_text=f"[follow-up] {parsed.intent.value}",
        classifier_used=CLASSIFIER_RULE,
    )
    outcome = await intent_layer._dispatcher.dispatch(synthesised, user, db)
    await intent_layer._send_outcome(chat_id, outcome)

    from backend import analytics
    analytics.track(
        "intent_followup_tapped",
        user_id=user.id,
        properties={"intent": parsed.intent.value},
    )
    return True


async def _handle_confirm_callback(
    db: AsyncSession,
    chat_id: int,
    user,
    state: dict | None,
    *,
    action: str,
) -> bool:
    """Resolve a [✅ Đúng] / [❌ Không phải] tap."""
    from backend import analytics

    if state is None or state.get("flow") != pending_action.FLOW_PENDING_ACTION:
        await send_message(
            chat_id,
            "Mình không tìm thấy yêu cầu nào đang chờ xác nhận 🌱",
        )
        return True

    intent = state.get("intent")
    params = state.get("parameters") or {}
    await pending_action.clear(db, user)

    if action != "yes":
        await send_message(
            chat_id,
            "OK, bỏ qua nhé! Bạn nói lại giúp mình một câu khác xem 🌱",
        )
        analytics.track(
            "intent_confirm_rejected",
            user_id=user.id,
            properties={"intent": intent},
        )
        return True

    # Execute the action. Currently only ACTION_RECORD_SAVING is wired
    # — other action types fall back to a "not implemented" message.
    if intent == IntentType.ACTION_RECORD_SAVING.value:
        amount = float(params.get("amount", 0))
        if amount <= 0:
            await send_message(
                chat_id,
                "Mình không thấy số tiền — bạn gõ lại như 'tiết kiệm 1tr' nhé.",
            )
            return True
        expense_data = ExpenseCreate(
            amount=amount,
            merchant="Tiết kiệm",
            note="action_record_saving",
            source="manual",
            category="saving",
            expense_date=date.today(),
        )
        expense = await expense_service.create_expense(db, user.id, expense_data)
        await send_transaction_confirmation(db, expense)
        analytics.track(
            "intent_confirm_accepted",
            user_id=user.id,
            properties={"intent": intent, "amount": int(amount)},
        )
        return True

    await send_message(
        chat_id,
        "Mình đã hiểu nhưng tính năng này chưa sẵn sàng — coming soon nhé! 🚀",
    )
    return True


async def _handle_clarify_callback(
    db: AsyncSession,
    chat_id: int,
    user,
    state: dict | None,
    *,
    index: str,
) -> bool:
    """Resolve a clarification button tap.

    The button label is the user's clarification answer — re-classify
    that label as if the user typed it, with the original parameters
    merged in.
    """
    if state is None or state.get("flow") != pending_action.FLOW_AWAITING_CLARIFY:
        await send_message(
            chat_id,
            "Câu hỏi này đã hết hạn rồi 🌱 — bạn hỏi lại giúp mình nhé.",
        )
        return True

    # We don't have access to the button label text from callback_data
    # alone — but the original intent was already classified. Re-treat
    # the situation as a confident execution of the original intent.
    await intent_layer.classify_and_dispatch(
        db=db,
        chat_id=chat_id,
        user=user,
        text=state.get("raw_text") or "",
    )
    return True
