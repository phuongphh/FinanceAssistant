"""Handler for ``ACTION_QUICK_TRANSACTION`` — quick expense logging.

Triggered when the LLM classifier tags a message like "170k ăn trưa"
with high confidence. The classifier prompt only extracts ``amount``
(and sometimes ``merchant``), so we re-parse the raw text via the
canonical ``_PARSE_PROMPT`` to get a reliable amount + merchant pair,
create the expense, and send the rich confirmation card directly.

Why this handler sends its own Telegram message and returns ``""``:
the standard flow has the dispatcher wrap returned text with
personality and ``_send_outcome`` deliver it via ``send_message``.
Quick transactions need the rich card with inline keyboard
(``send_transaction_confirmation``), which doesn't fit the plain-text
return shape. Returning an empty string lets ``_send_outcome`` skip
the duplicate send while keeping the dispatcher contract intact.
"""
from __future__ import annotations

import json
import logging
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.handlers.transaction import send_transaction_confirmation
from backend.intent.handlers.base import IntentHandler
from backend.intent.intents import IntentResult
from backend.models.user import User
from backend.schemas.expense import ExpenseCreate
from backend.services import expense_service
from backend.services.llm_service import call_llm

logger = logging.getLogger(__name__)


# Same prompt the legacy fallback in message.py uses — kept here so the
# behaviour is identical to what users had before the intent layer
# started classifying these messages.
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


_FALLBACK_REPLY = (
    "Mình chưa nhận ra số tiền trong câu này 🌱 — bạn thử gõ rõ hơn"
    " như '50k cà phê' hoặc '150 ngàn ăn trưa' nhé."
)


class ActionQuickTransactionHandler(IntentHandler):
    async def handle(
        self, intent: IntentResult, user: User, db: AsyncSession
    ) -> str:
        text = (intent.raw_text or "").strip()
        params = intent.parameters or {}

        amount, merchant = await self._extract(text, params, db, user)
        if amount is None or amount <= 0:
            return _FALLBACK_REPLY

        expense_data = ExpenseCreate(
            amount=float(amount),
            merchant=merchant or text,
            note=text,
            source="manual",
            expense_date=date.today(),
        )
        expense = await expense_service.create_expense(db, user.id, expense_data)
        await send_transaction_confirmation(db, expense)
        # Confirmation card already sent — tell the dispatcher there's
        # nothing more to deliver via the normal text path.
        return ""

    async def _extract(
        self,
        text: str,
        params: dict,
        db: AsyncSession,
        user: User,
    ) -> tuple[float | None, str | None]:
        # Trust classifier params if amount is already parsed cleanly —
        # saves an LLM call on the hot path. Merchant is optional in the
        # classifier prompt, so we accept whatever's there.
        try:
            amount = float(params.get("amount")) if params.get("amount") else None
        except (TypeError, ValueError):
            amount = None
        merchant = params.get("merchant") if isinstance(
            params.get("merchant"), str
        ) else None

        if amount and amount > 0:
            return amount, merchant

        # Classifier didn't give us a usable amount — fall back to the
        # legacy parser. Cached by raw text, so retries are free.
        try:
            raw = await call_llm(
                _PARSE_PROMPT.format(text=text),
                task_type="parse_manual",
                db=db,
                user_id=user.id,
                use_cache=True,
                shared_cache=False,
            )
            cleaned = "\n".join(
                line for line in raw.splitlines() if not line.startswith("```")
            )
            parsed = json.loads(cleaned)
        except Exception:
            logger.exception("Quick-transaction LLM parse failed for %r", text)
            return None, None

        if not parsed.get("is_expense"):
            return None, None
        try:
            parsed_amount = float(parsed.get("amount", 0))
        except (TypeError, ValueError):
            parsed_amount = 0.0
        if parsed_amount <= 0:
            return None, None
        parsed_merchant = parsed.get("merchant") or merchant
        return parsed_amount, parsed_merchant
