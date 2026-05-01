"""Handle free-text Telegram messages.

Phase 3.5 routing order (after the worker has dispatched commands and
wizards):

  1. Report intent (legacy, still served by ``report_service``).
  2. ``IntentPipeline.classify`` — covers ~75% of user queries via
     rule-based patterns. Confident matches dispatch immediately and
     return.
  3. LLM transaction parser — fallback for "vừa chi 200k ăn trưa"
     style messages that don't match any query pattern.
  4. ``IntentDispatcher`` UNCLEAR / OOS response — final fallback so
     the user always gets a friendly reply (no silent fail).
"""
from __future__ import annotations

import json
import logging
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from backend import analytics
from backend.bot.handlers import free_form_text as intent_layer
from backend.bot.handlers.transaction import send_transaction_confirmation
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

# Below this confidence the intent layer hands off to the LLM transaction
# parser instead of dispatching. Above it (or any non-meta intent) we
# trust the rule match.
_INTENT_DISPATCH_CONFIDENCE = 0.5


async def _send_report(db: AsyncSession, chat_id: int, telegram_id: int, text: str = "") -> None:
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

    # Phase 3.5 — classify before falling back to the LLM transaction
    # parser. A confident, non-meta match means the user asked a query
    # we already know how to handle, so the LLM round-trip is skipped.
    intent_result = await intent_layer._pipeline.classify(text)
    analytics.track(
        intent_layer.EVENT_INTENT_CLASSIFIED,
        user_id=user.id,
        properties={
            "intent": intent_result.intent.value,
            "confidence": round(intent_result.confidence, 3),
            "classifier": intent_result.classifier_used,
        },
    )

    if (
        intent_result.intent
        not in (IntentType.UNCLEAR, IntentType.OUT_OF_SCOPE)
        and intent_result.confidence >= _INTENT_DISPATCH_CONFIDENCE
    ):
        response = await intent_layer._dispatcher.dispatch(
            intent_result, user, db
        )
        await send_message(chat_id, response)
        analytics.track(
            intent_layer.EVENT_INTENT_HANDLER_EXECUTED,
            user_id=user.id,
            properties={
                "intent": intent_result.intent.value,
                "confidence": round(intent_result.confidence, 3),
            },
        )
        return True

    # Try the LLM transaction parser — covers free-form expense entry
    # like "vừa chi 200k ăn trưa" that doesn't match a query pattern.
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

    # Final fallback: friendly unclear / out-of-scope reply through the
    # dispatcher so messaging stays consistent.
    response = await intent_layer._dispatcher.dispatch(intent_result, user, db)
    await send_message(chat_id, response)
    analytics.track(
        intent_layer.EVENT_INTENT_UNCLEAR,
        user_id=user.id,
        properties={"intent": intent_result.intent.value},
    )
    return True
