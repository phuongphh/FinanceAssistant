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
import re
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.handlers import free_form_text as intent_layer
from backend.bot.handlers.transaction import send_transaction_confirmation
from backend.bot.keyboards.transaction_keyboard import transaction_source_keyboard
from backend.intent import pending_action
from backend.intent.income_semantics import is_duoc_money_in
from backend.intent.dispatcher import (
    OUTCOME_CLARIFY_SENT,
    OUTCOME_CONFIRM_SENT,
    OUTCOME_OUT_OF_SCOPE,
    OUTCOME_UNCLEAR,
)
from backend.intent.intents import IntentType
from backend.schemas.expense import ExpenseCreate, ExpenseUpdate
from backend.services import expense_service, report_service, wizard_service
from backend.services.dashboard_service import get_user_by_telegram_id
from backend.services.expense_source_resolver import apply_default_source
from backend.services.llm_service import call_llm
from backend.services.telegram_service import send_message
from backend.wealth.amount_parser import parse_amount

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

# Quick-syntax for manual transactions. We deliberately keep the
# entry point narrow so that ordinary chat ("nhắc tôi mua sữa 50k
# chiều mai", "200 nghìn là bao nhiêu USD") doesn't get hijacked
# into the expense pipeline. The body must EITHER carry an explicit
# +/- sign, OR begin with the amount token (allowing an optional
# leading currency word/symbol). Anything else is left to the intent
# pipeline.
_AMOUNT_TOKEN_PATTERN = (
    r"\d{1,3}(?:[.,]\d{3})+"
    r"|\d+(?:[.,]\d+)?(?:\s*(?:tỷ|ty|tỉ|triệu|trieu|tr|nghìn|nghin|ngàn|ngan|k|đ|d|vnđ|vnd)(?:\s*\d+)?)?"
)

_SIGNED_TX_RE = re.compile(
    r"^\s*(?P<sign>[+-])\s*(?P<body>.+?)\s*$",
    re.IGNORECASE,
)

_AMOUNT_LED_TX_RE = re.compile(
    rf"^\s*(?P<body>(?:{_AMOUNT_TOKEN_PATTERN})(?:\s+.{{0,500}})?)\s*$",
    re.IGNORECASE,
)

_AMOUNT_TOKEN_RE = re.compile(
    rf"(?P<amt>{_AMOUNT_TOKEN_PATTERN})",
    re.IGNORECASE,
)

# Stricter amount matcher for the "được" money-in fast-path. Unlike
# ``_AMOUNT_TOKEN_RE`` it REQUIRES a currency unit (or dotted-thousands
# grouping) so a plain count is never mistaken for money: "được mẹ cho 2
# quả cam" must NOT record a 2đ money-in and steal the message from the
# intent pipeline. This mirrors the Tier-1 YAML rule, which also demands
# a money suffix for this shape. Keep the unit list in sync with
# ``_AMOUNT_TOKEN_PATTERN`` above.
_DUOC_AMOUNT_RE = re.compile(
    r"(?P<amt>\d{1,3}(?:[.,]\d{3})+(?:\s*(?:tỷ|ty|tỉ|triệu|trieu|tr|nghìn|nghin|ngàn|ngan|k|đ|d|vnđ|vnd))?"
    r"|\d+(?:[.,]\d+)?\s*(?:tỷ|ty|tỉ|triệu|trieu|tr|nghìn|nghin|ngàn|ngan|k|đ|d|vnđ|vnd)(?:\s*\d+)?)",
    re.IGNORECASE,
)

# Question-shaped inputs ("200k là bao nhiêu USD") must NOT be parsed as
# expense entries. The list is narrow on purpose — real expense notes
# don't use these phrases.
_QUESTION_HINT_RE = re.compile(
    r"\?|\bbao nhiêu\b|\bbao lâu\b|\bkhi nào\b|\bở đâu\b|\bthế nào\b|\blà gì\b|\bcó phải\b|\bcó không\b",
    re.IGNORECASE,
)
_CARD_SOURCE_RE = re.compile(r"trả\s+bằng\s+thẻ\s+(.+)$", re.IGNORECASE)


async def _extract_credit_card_source(db: AsyncSession, user_id, text: str) -> tuple[str | None, str | None]:
    match = _CARD_SOURCE_RE.search(text)
    if not match:
        return None, None
    bank = match.group(1).strip(" .,:;!-")
    if not bank:
        return None, None
    from backend.models.credit_card import CreditCard
    from sqlalchemy import func, select

    row = await db.execute(
        select(CreditCard).where(
            CreditCard.user_id == user_id,
            func.lower(CreditCard.bank_name) == bank.lower(),
        )
    )
    card = row.scalar_one_or_none()
    if card is None:
        return None, None
    return "credit_card", str(card.id)


def _parse_signed_transaction(text: str) -> dict | None:
    if _QUESTION_HINT_RE.search(text):
        return None
    signed = _SIGNED_TX_RE.match(text)
    if signed:
        sign = signed.group("sign")
        body = (signed.group("body") or "").strip()
    else:
        amount_led = _AMOUNT_LED_TX_RE.match(text)
        if not amount_led:
            return None
        sign = None
        body = (amount_led.group("body") or "").strip()

    amount_match = _AMOUNT_TOKEN_RE.search(body)
    if not amount_match:
        return None

    if not sign and re.fullmatch(r"\d+", body):
        return None

    amount_token = amount_match.group("amt").strip()
    amount_decimal = parse_amount(amount_token)
    if amount_decimal is None or amount_decimal <= 0:
        return None

    merchant = f"{body[:amount_match.start()]} {body[amount_match.end():]}"
    merchant = re.sub(r"\s+", " ", merchant).strip(" ,-+;:")[:500]

    return {
        "amount": float(amount_decimal),
        "merchant": merchant,
        "note": text[:1000],
        "transaction_type": "money_in" if sign == "+" else "expense",
    }


def _parse_duoc_money_in(text: str) -> dict | None:
    """Parse the "được <giver> cho/tặng/lì xì/thưởng… <amount>" money-in shape.

    Vietnamese users log received money with the verb **"được"** far more
    often than with a leading ``+``. The Chi tiêu menu promises that
    "được bố cho 500k", "được thưởng 200k", "được lì xì 50k" are recorded
    as money-in, so we catch them here — before the intent pipeline — and
    route straight to the source-picker wizard, mirroring the ``+`` path.

    Returns a money-in ``parsed`` dict (same shape as
    :func:`_parse_signed_transaction`) or ``None`` when the text isn't a
    "được"-gift with an extractable amount.
    """
    if _QUESTION_HINT_RE.search(text):
        return None
    if not is_duoc_money_in(text):
        return None

    # Require a currency-denominated amount (see ``_DUOC_AMOUNT_RE``) so
    # non-cash gifts like "được mẹ cho 2 quả cam" fall through to the
    # intent pipeline instead of being booked as a 2đ money-in.
    amount_match = _DUOC_AMOUNT_RE.search(text)
    if not amount_match:
        return None
    amount_token = amount_match.group("amt").strip()
    amount_decimal = parse_amount(amount_token)
    if amount_decimal is None or amount_decimal <= 0:
        return None

    merchant = f"{text[:amount_match.start()]} {text[amount_match.end():]}"
    merchant = re.sub(r"\s+", " ", merchant).strip(" ,-+;:")
    # Drop the leading "được" so the source label reads "bố cho" /
    # "thưởng" / "lì xì" rather than "được bố cho".
    merchant = re.sub(r"(?i)^được\s+", "", merchant)[:500]

    return {
        "amount": float(amount_decimal),
        "merchant": merchant,
        "note": text[:1000],
        "transaction_type": "money_in",
    }


async def _start_source_prompt(
    db: AsyncSession, chat_id: int, user, parsed: dict
) -> bool:
    tx_type = parsed["transaction_type"]
    await wizard_service.start_flow(
        db,
        user.id,
        "transaction_source_select",
        "source_type",
        draft=parsed,
    )
    prompt = (
        "Tiền vào nguồn nào?" if tx_type == "money_in" else "Tiền chi từ nguồn nào?"
    )
    merchant = (parsed.get("merchant") or "").strip()
    sign = "+" if tx_type == "money_in" else "-"
    amount_line = f"{sign}{parsed['amount']:,.0f}đ"
    detail = f"{merchant} · {amount_line}" if merchant else amount_line
    await send_message(
        chat_id,
        f"{prompt}\n{detail}",
        reply_markup=transaction_source_keyboard(tx_type),
    )
    return True


async def _record_signed_expense_with_default(
    db: AsyncSession, user, parsed: dict
) -> bool:
    """Record an expense from the signed/amount-led fast-path using the
    user's ``default_expense_source``.

    Returns True when the expense was created and the confirmation card
    was sent — caller then skips the wizard. Returns False when the user
    has no default source configured (caller falls back to the picker).
    """
    merchant = (parsed.get("merchant") or parsed.get("note") or "Giao dịch").strip()
    expense_data = ExpenseCreate(
        amount=float(parsed["amount"]),
        merchant=merchant or "Giao dịch",
        note=parsed.get("note"),
        source="manual",
        category="other",
        expense_date=date.today(),
    )
    resolved = await apply_default_source(db, user.id, expense_data)
    if not resolved.source_type:
        return False
    expense = await expense_service.create_expense(db, user.id, resolved)
    await send_transaction_confirmation(db, expense)
    return True


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


async def _maybe_handle_amount_edit(
    db: AsyncSession, user, chat_id: int, text: str
) -> bool:
    """If user is in the transaction_amount_edit wizard, apply the new amount."""
    state = user.wizard_state or {}
    if state.get("flow") != "transaction_amount_edit":
        return False
    draft = dict(state.get("draft") or {})
    expense_id = draft.get("expense_id")
    if not expense_id:
        await wizard_service.clear(db, user.id)
        return False

    try:
        amount = parse_amount(text)
    except Exception:
        amount = None
    if amount is None or amount <= 0:
        await send_message(
            chat_id,
            "Mình chưa hiểu số tiền — bạn nhập lại giúp mình nhé (ví dụ: 45k, 1.2tr).",
        )
        return True

    updated = await expense_service.update_expense(
        db, user.id, expense_id, ExpenseUpdate(amount=float(amount))
    )
    await wizard_service.clear(db, user.id)
    if updated is None:
        await send_message(chat_id, "Giao dịch này mình không thấy nữa 🫣")
        return True

    original_message_id = draft.get("message_id")
    original_chat_id = draft.get("chat_id", chat_id)
    if original_message_id is not None:
        from backend.bot.handlers.callbacks import _rerender_transaction_message

        await _rerender_transaction_message(
            original_chat_id,
            original_message_id,
            updated,
            edited=True,
            db=db,
        )
    else:
        await send_message(chat_id, f"Đã cập nhật số tiền thành {float(amount):,.0f}đ")
    return True


async def handle_report_command(db: AsyncSession, message: dict) -> None:
    """Handle /report command — extracts Telegram data, delegates to service."""
    chat_id = message["chat"]["id"]
    telegram_id = (message.get("from") or {}).get("id", chat_id)
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

    # Issue #897 — capture amount-edit reply for an existing transaction
    # before any other text routing.
    if await _maybe_handle_amount_edit(db, user, chat_id, text):
        return True

    # Fast-path for explicit +/- expense syntax before generic intent routing.
    signed = _parse_signed_transaction(text)
    if signed is not None:
        if signed["transaction_type"] == "expense":
            if await _record_signed_expense_with_default(db, user, signed):
                return True
        return await _start_source_prompt(db, chat_id, user, signed)

    # Fast-path for "được <giver> cho/tặng/lì xì/thưởng <amount>" money-in
    # (e.g. "được bố cho 500k"). The Chi tiêu menu promises these are
    # recorded as money-in, so we route them to the source picker just
    # like a leading "+", rather than letting them fall through to the
    # expense pipeline.
    duoc_money_in = _parse_duoc_money_in(text)
    if duoc_money_in is not None:
        return await _start_source_prompt(db, chat_id, user, duoc_money_in)

    # Phase 3.5 — full intent flow with confirm/clarify state handling.
    outcome = await intent_layer.classify_and_dispatch(
        db=db, chat_id=chat_id, user=user, text=text
    )

    if outcome is None:
        return False  # empty text — shouldn't happen given the early return

    # Confident execution OR terminal outcomes (clarify/confirm/OOS) — done.
    if outcome.kind not in (OUTCOME_UNCLEAR,) and outcome.intent != IntentType.UNCLEAR:
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

    if parsed and parsed.get("is_expense") and float(parsed.get("amount", 0)) > 0:
        source_type, source_card_id = await _extract_credit_card_source(db, user.id, text)
        expense_data = ExpenseCreate(
            amount=float(parsed["amount"]),
            merchant=parsed.get("merchant") or text,
            note=text,
            source="manual",
            expense_date=date.today(),
            source_type=source_type,
            source_credit_card_id=source_card_id,
        )
        expense_data = await apply_default_source(db, user.id, expense_data)
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
    if not (data.startswith("intent_") or data.startswith(follow_up.CALLBACK_PREFIX)):
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
        expense_data = await apply_default_source(db, user.id, expense_data)
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
