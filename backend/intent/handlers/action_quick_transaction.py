"""Handler for ``ACTION_QUICK_TRANSACTION`` — quick expense logging.

Triggered when the LLM classifier tags a message like "170k ăn trưa"
with high confidence. The classifier prompt only extracts ``amount``
(and sometimes ``merchant``), so we re-parse the raw text via the
canonical parser prompts to get reliable item(s), create the expense(s),
and send the rich confirmation card directly.

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
import re
import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.handlers.transaction import (
    send_transaction_batch_confirmation,
    send_transaction_confirmation,
)
from backend.bot.utils.transaction_date_extractor import (
    extract_transaction_date,
    strip_span,
)
from backend.intent.clarifier import build_message_from_key
from backend.intent.handlers.base import IntentHandler
# Income vs. expense semantics live in ONE place —
# ``backend/intent/income_semantics.py``. The message-layer fast-path
# (which records the transaction), the rule-based tier, and this expense
# handler (defence-in-depth income guard) must all agree, so we import
# the shared detectors rather than maintain a divergent copy. Diverging
# copies were the root cause of "được bố cho 500k" being silently
# mis-recorded as an expense. The ``_`` aliases stay importable for
# backward compatibility (tests reach into this module).
from backend.intent.income_semantics import (
    has_leading_plus_sign as _has_leading_plus_sign,
    looks_like_income as _looks_like_income,
)
from backend.intent.intents import IntentResult
from backend.models.user import User
from backend.schemas.expense import ExpenseCreate
from backend.services import expense_service
from backend.services.expense_source_resolver import apply_default_source
from backend.services.llm_service import call_llm, invalidate_cache

logger = logging.getLogger(__name__)

__all__ = [
    "ActionQuickTransactionHandler",
    "_has_leading_plus_sign",
    "_looks_like_income",
]


# Same prompt the legacy fallback in message.py uses — kept here so the
# behaviour is identical to what users had before the intent layer
# started classifying these messages.
_SINGLE_PARSE_PROMPT = """Parse chi tiêu từ text sau và trả về JSON:
"{text}"

Trả về JSON với format:
{{"amount": <số>, "merchant": "<tên hoặc mô tả ngắn>", "is_expense": <true|false>}}

Quy tắc:
- Nếu text bắt đầu bằng "+" trước số → đây là TIỀN VÀO (income), is_expense: false
- Nếu text bắt đầu bằng "-" trước số → là chi tiêu, is_expense: true
- Nếu có số tiền và mô tả (không có dấu +/-) → is_expense: true
- Nếu là câu hỏi, tin nhắn thông thường, không phải chi tiêu → is_expense: false, amount: 0
- "k" hoặc "K" cuối số = × 1000: 50k = 50000, 150k = 150000
- merchant = nơi mua hoặc mô tả ngắn gọn nhất

Chỉ trả về JSON, không giải thích."""


_MULTI_PARSE_PROMPT = """Parse một hoặc nhiều khoản chi tiêu từ text sau và trả về JSON:
"{text}"

Trả về JSON với format:
{{
  "is_expense": <true|false>,
  "items": [
    {{"amount": <số>, "merchant": "<mô tả ngắn>", "category_hint": "<food|transport|shopping|health|education|entertainment|utility|saving|investment|gift|transfer|other|needs_review>"}}
  ]
}}

Quy tắc:
- Nếu text bắt đầu bằng "+" trước số → đây là TIỀN VÀO (income), is_expense: false.
- Nếu text bắt đầu bằng "-" trước số → là chi tiêu, is_expense: true.
- Nếu có nhiều cụm mô tả + số tiền, hãy tách thành nhiều items.
- Ví dụ: "tiền xăng 50k, ăn trưa 50k" → 2 items.
- Nếu chỉ có một số tiền tổng cho nhiều món, ví dụ "ăn tối và trà sữa 400k" → 1 item.
- "k" hoặc "K" cuối số = × 1000: 50k = 50000, 150k = 150000.
- category_hint chỉ dùng các code trong schema; nếu không chắc dùng "needs_review".

Chỉ trả về JSON, không giải thích."""


# The lookahead after the unit stops "tr"/"k" from matching the prefix of a
# word ("tr" in "trên", "k" in "kem") and inflating the amount ×1,000,000.
# ``[^\W\d_]`` is "a letter"; the inner ``(?!rưỡi|ruoi)`` lets a glued
# half-word through, matching backend.wealth.amount_parser.
_AMOUNT_RE = re.compile(
    r"(?<!\w)(\d+(?:[.,]\d+)?)(?:\s*(k|K|ngàn|nghìn|ngan|nghin|tr|triệu|trieu)(?!(?!rưỡi|ruoi)[^\W\d_]))?",
    re.IGNORECASE,
)
_SPLIT_RE = re.compile(r"\s*(?:,|\+|\n|\s+và\s+)\s*", re.IGNORECASE)
_LEADING_TIME_RE = re.compile(
    r"^(?:tối qua|trưa nay|sáng nay|chiều nay|hôm nay|hôm qua|vừa|mới|nay)\s+",
    re.IGNORECASE,
)

_CATEGORY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("transport", ("xăng", "grab", "taxi", "xe", "bus", "vé xe", "đổ xăng")),
    (
        "food",
        ("ăn", "cơm", "trưa", "tối", "sáng", "cafe", "cà phê", "trà sữa", "phở", "bún"),
    ),
    ("shopping", ("mua", "áo", "quần", "giày", "shopee", "lazada")),
    ("health", ("thuốc", "khám", "bệnh viện", "nha khoa")),
    ("education", ("sách", "học", "khóa học", "học phí")),
    ("entertainment", ("phim", "game", "karaoke", "netflix")),
    ("utility", ("điện", "nước", "internet", "wifi", "điện thoại")),
)


@dataclass(frozen=True)
class ParsedExpenseItem:
    amount: float
    merchant: str
    category_hint: str = "other"


_FALLBACK_REPLY = (
    "Mình chưa nhận ra số tiền trong câu này 🌱 — bạn thử gõ rõ hơn"
    " như '50k cà phê' hoặc '150 ngàn ăn trưa' nhé."
)


class ActionQuickTransactionHandler(IntentHandler):
    async def handle(self, intent: IntentResult, user: User, db: AsyncSession) -> str:
        text = (intent.raw_text or "").strip()
        params = intent.parameters or {}

        # Guardrail: if the message reads as income (nhận lương, thưởng,
        # cổ tức…), refuse to record it as an expense and route the user
        # to the proper income flow (#656, #661). Better a soft handoff
        # than a silent wrong write.
        if _looks_like_income(text):
            logger.info(
                "Quick-transaction handler skipped — income semantics detected: %r",
                text,
            )
            return build_message_from_key(
                "income_detected_in_expense_flow", user
            )

        # Tier-2 must mirror the Tier-1 fast-path: pull any
        # ``ngày dd/mm[/yyyy]`` hint out before item-parsing so the
        # date digits don't get re-interpreted as a second amount, and
        # so the recorded ``expense_date`` matches what the user typed.
        extracted_date = extract_transaction_date(text)
        expense_date_value = (
            extracted_date.value if extracted_date is not None else date.today()
        )
        parse_text = (
            strip_span(text, extracted_date.span)
            if extracted_date is not None
            else text
        )

        items = await self._extract_items(parse_text, params, db, user)
        if not items:
            return _FALLBACK_REPLY

        if len(items) == 1:
            item = items[0]
            expense_data = ExpenseCreate(
                amount=float(item.amount),
                merchant=item.merchant or parse_text,
                category=item.category_hint,
                note=text,
                source="manual",
                expense_date=expense_date_value,
            )
            expense_data = await apply_default_source(db, user.id, expense_data)
            expense = await expense_service.create_expense(db, user.id, expense_data)
            await send_transaction_confirmation(db, expense)
        else:
            batch_id = str(uuid.uuid4())
            expenses = []
            for index, item in enumerate(items, start=1):
                expense_data = ExpenseCreate(
                    amount=float(item.amount),
                    merchant=item.merchant or parse_text,
                    category=item.category_hint,
                    note=text,
                    source="manual",
                    expense_date=expense_date_value,
                    raw_data={
                        "batch_id": batch_id,
                        "batch_size": len(items),
                        "batch_index": index,
                        "raw_text": text,
                    },
                )
                expense_data = await apply_default_source(
                    db, user.id, expense_data
                )
                expenses.append(
                    await expense_service.create_expense(db, user.id, expense_data)
                )
            await send_transaction_batch_confirmation(db, expenses, batch_id=batch_id)
        # Confirmation card already sent — tell the dispatcher there's
        # nothing more to deliver via the normal text path.
        return ""

    async def _extract_items(
        self,
        text: str,
        params: dict,
        db: AsyncSession,
        user: User,
    ) -> list[ParsedExpenseItem]:
        amount_mentions = _count_amount_mentions(text)

        # Classifier params only represent one transaction. If the raw
        # text contains multiple amount tokens, parse the raw text first
        # so messages like "tiền xăng 50k, ăn trưa 50k" are not merged.
        if amount_mentions >= 2:
            heuristic_items = _parse_items_heuristically(text)
            if len(heuristic_items) > 1:
                return heuristic_items

            llm_items = await self._extract_items_with_llm(text, db, user)
            if llm_items:
                return llm_items

        # Fast path: trust classifier params only for single-item text.
        try:
            amount = float(params.get("amount")) if params.get("amount") else None
        except (TypeError, ValueError):
            amount = None
        merchant = (
            params.get("merchant") if isinstance(params.get("merchant"), str) else None
        )

        if amount and amount > 0:
            return [
                ParsedExpenseItem(
                    amount=amount,
                    merchant=merchant or text,
                    category_hint=_guess_category(merchant or text),
                )
            ]

        single_item = await self._extract_single_item_with_llm(text, db, user)
        if single_item:
            return [single_item]

        # Safety net. Until now the LLM was the ONLY thing
        # standing between a perfectly parseable "ăn trưa 180k" and the
        # "mình chưa nhận ra số tiền" apology: the classifier hands us
        # ``amount`` only when it feels like it, and the fallback
        # ``parse_manual`` call can fail for reasons that have nothing to
        # do with the message — Groq blip, 5s timeout, GROQ_API_KEY
        # missing on that box, budget cap, or one bad JSON reply pinned
        # in ``llm_cache`` for 30 days. Any of those turned capture into
        # a *reproducible* dead end for that exact sentence.
        #
        # Amount-led text ("180k ăn trưa") never hit this because the
        # Tier-1 regex in bot/handlers/message.py catches it before the
        # intent layer, which is why the two shapes behaved so
        # differently in the same deploy. Description-led text deserves
        # the same deterministic floor: capture is the core loop and must
        # not depend on a network round-trip when the text is
        # unambiguous. Regex owns digits + đơn vị; the LLM still owns the
        # fuzzy cases (số viết bằng chữ, câu phức, nhiều khoản).
        heuristic_item = _parse_single_item_heuristically(text)
        if heuristic_item is not None:
            logger.info(
                "Quick-transaction rescued by heuristic parse (LLM gave nothing): %r",
                text,
            )
            return [heuristic_item]
        return []

    async def _extract_items_with_llm(
        self,
        text: str,
        db: AsyncSession,
        user: User,
    ) -> list[ParsedExpenseItem]:
        try:
            # Groq Llama 3.3 70B handles the structured-JSON parse in
            # sub-second; DeepSeek V4-Flash took 4-12s for the same
            # call, which dominated the wait for batch-typing users
            # ("tiền xăng 50k, ăn trưa 50k, cà phê 20k"). 5s timeout
            # leaves headroom for the slightly longer JSON output
            # compared to single-token intent classify.
            raw = await call_llm(
                _MULTI_PARSE_PROMPT.format(text=text),
                task_type="parse_manual_multi",
                db=db,
                user_id=user.id,
                use_cache=True,
                shared_cache=False,
                provider="groq",
                timeout=5.0,
            )
            parsed = _load_json_response(raw)
        except Exception:
            logger.exception("Multi quick-transaction LLM parse failed for %r", text)
            return []

        if not parsed.get("is_expense"):
            return []
        items = parsed.get("items")
        if not isinstance(items, list):
            return []
        return _coerce_parsed_items(items, fallback_text=text)

    async def _extract_single_item_with_llm(
        self,
        text: str,
        db: AsyncSession,
        user: User,
    ) -> ParsedExpenseItem | None:
        # Classifier didn't give us a usable amount — fall back to the
        # legacy parser. Cached by raw text, so retries are free.
        # Groq (same rationale as the multi-item variant): sub-second
        # vs DeepSeek's 4-12s tail.
        prompt = _SINGLE_PARSE_PROMPT.format(text=text)
        try:
            raw = await call_llm(
                prompt,
                task_type="parse_manual",
                db=db,
                user_id=user.id,
                use_cache=True,
                shared_cache=False,
                provider="groq",
                timeout=5.0,
            )
        except Exception:
            # Nothing came back, so nothing was cached — no entry to evict.
            logger.exception("Quick-transaction LLM parse failed for %r", text)
            return None

        # Split from the call on purpose. ``call_llm`` writes the response to
        # ``llm_cache`` the moment the provider answers, *before* anyone can
        # judge whether the answer is JSON at all — so a decode failure here
        # means a malformed reply is already pinned for the full TTL. Folding
        # this into the try above (as the first cut did) skipped straight past
        # the eviction below and left the user replaying that same garbage on
        # every retry.
        try:
            parsed = _load_json_response(raw)
        except Exception:
            logger.warning(
                "Quick-transaction LLM returned non-JSON for %r", text, exc_info=True
            )
            await self._forget_cached_parse(prompt, db, user, text)
            return None

        item = _single_item_from_parsed(parsed, fallback_text=text)
        if item is None:
            # "Free retries" cut both ways: a reply we can't use is
            # cached just as eagerly as a good one, so the user retyping
            # the same sentence replays the same dud for the whole TTL
            # instead of re-asking the model. Drop it.
            await self._forget_cached_parse(prompt, db, user, text)
        return item

    async def _forget_cached_parse(
        self,
        prompt: str,
        db: AsyncSession,
        user: User,
        text: str,
    ) -> None:
        """Evict one unusable ``parse_manual`` reply, best effort.

        Never let cache bookkeeping sink the capture — the heuristic
        fallback upstream still has a shot at this message.
        """
        try:
            await invalidate_cache(
                db,
                task_type="parse_manual",
                prompt=prompt,
                user_id=user.id,
                shared_cache=False,
            )
        except Exception:
            logger.warning(
                "Could not invalidate parse_manual cache for %r",
                text,
                exc_info=True,
            )


def _load_json_response(raw: str) -> dict:
    cleaned = "\n".join(
        line for line in raw.splitlines() if not line.strip().startswith("```")
    )
    return json.loads(cleaned)


def _count_amount_mentions(text: str) -> int:
    return len(_AMOUNT_RE.findall(text or ""))


def _parse_items_heuristically(text: str) -> list[ParsedExpenseItem]:
    clauses = [part.strip() for part in _SPLIT_RE.split(text or "") if part.strip()]
    parsed: list[ParsedExpenseItem] = []

    for clause in clauses:
        matches = list(_AMOUNT_RE.finditer(clause))
        if len(matches) != 1:
            continue
        match = matches[0]
        amount = _parse_amount_match(match)
        if amount <= 0:
            continue
        merchant = _clean_merchant(f"{clause[:match.start()]} {clause[match.end():]}")
        if not merchant:
            continue
        parsed.append(
            ParsedExpenseItem(
                amount=amount,
                merchant=merchant,
                category_hint=_guess_category(merchant),
            )
        )

    return parsed if len(parsed) > 1 else []


# Smallest bare (unsuffixed) number we will read as VND. "cà phê 45" is
# far more likely a quantity, a table number or a typo than 45 đồng,
# whereas any number carrying a unit ("45k", "1tr") is unambiguous and
# always accepted. 50.000 / 50,000 also clear the bar once
# ``_parse_amount_match`` expands the thousands separators.
_MIN_PLAIN_AMOUNT = 1_000


# "1tr2" and "1tr rưỡi" mean 1.200.000 / 1.500.000, but ``_AMOUNT_RE``
# only sees the "1tr" half. Reading that as a flat 1.000.000 would book a
# confidently wrong number, so the heuristic bails and lets the LLM —
# which understands the idiom — take the message.
_COMPOUND_TAIL_RE = re.compile(r"\s*(?:\d|rưỡi|ruoi)", re.IGNORECASE)

# A separator glued to more digits means ``_AMOUNT_RE`` only captured a
# slice of a longer number: in "tiền nhà 1.500.000" it stops after
# "1.500". Booking 1.500đ for a 1,5-triệu rent is the exact failure mode
# this parser exists to avoid, so a partial capture is a decline.
_GROUPED_TAIL_RE = re.compile(r"[.,]\d")

# The user asking *about* an amount is not the user spending it. The LLM
# gets this right (``is_expense: false``), but the heuristic runs
# precisely when the LLM said nothing usable — and the dispatcher
# executes medium-confidence quick transactions without a confirmation
# step (backend/intent/dispatcher.py), so a wrong "yes" here is a silent
# write into the user's ledger. "ăn trưa 50k có đắt không?" must reach
# the fallback reply, never the create path.
_QUESTION_RE = re.compile(
    r"\?"                                          # "… 50k?"
    r"|\b(?:không|khong|ko|hông)\s*[?!.…]*$"       # "… có đắt không"
    r"|\b(?:nhỉ|nhi|hả|hử)\s*[?!.…]*$"             # "… đắt nhỉ"
    r"|\bbao nhiêu\b|\bbao nhieu\b",               # "ăn trưa bao nhiêu"
    re.IGNORECASE,
)

# Commenting on a price is not paying it either, and commentary does not
# have to be phrased as a question: "giá này 180k mắc quá" carries no "?",
# no "không", no "bao nhiêu", so ``_QUESTION_RE`` waves it straight through
# into the ledger. Judgement words about cost, and the intensifier tail
# Vietnamese hangs off them, are the tell that the sentence evaluates an
# amount rather than reporting one.
_COMMENTARY_RE = re.compile(
    r"\b(?:mắc|mac|đắt|dat|rẻ|re|chát|chat|hời|hoi)\b"  # "… 180k mắc quá"
    r"|\bgiá\s+(?:này|đó|kia)\b|\bgia\s+(?:nay|do|kia)\b"  # "giá này 180k"
    r"|\b(?:quá|qua|thế|the|vậy|vay|ghê|ghe)\s*[!.…]*$",  # "… 180k quá"
    re.IGNORECASE,
)


def _is_ratio_token(text: str, match: re.Match[str]) -> bool:
    """True when the number is a percentage, not money.

    "lãi suất 6%" reaching this handler must not become a 6đ expense.
    """
    return text[match.end():].lstrip().startswith("%")


def _has_compound_tail(text: str, match: re.Match[str]) -> bool:
    """True when a second half follows the amount ("1tr2", "1tr rưỡi")."""
    return bool(_COMPOUND_TAIL_RE.match(text[match.end():]))


def _is_partial_number(text: str, match: re.Match[str]) -> bool:
    """True when the match is a slice of a longer numeric run.

    "1.500.000" reaches ``_AMOUNT_RE`` as "1.500" followed by ".000".
    """
    before = text[:match.start()]
    if before and before[-1] in ".,":
        return True
    return bool(_GROUPED_TAIL_RE.match(text[match.end():]))


def _looks_like_a_question(text: str) -> bool:
    """True when the message asks about money rather than reporting it."""
    return bool(_QUESTION_RE.search(text))


def _looks_like_price_commentary(text: str) -> bool:
    """True when the message judges an amount instead of reporting a spend.

    Declining costs the user one fallback message; guessing wrong writes a
    transaction they never made, unconfirmed. Decline is the cheap side.
    """
    return bool(_COMMENTARY_RE.search(text))


def _parse_single_item_heuristically(text: str) -> ParsedExpenseItem | None:
    """Deterministic single-expense parse — no LLM, no network.

    Deliberately conservative: the message has already been classified
    as a quick transaction and cleared the income guard, so the only job
    left is reading one unambiguous amount. One money-looking token plus
    a non-empty description, or we decline and let the caller keep the
    honest "chưa nhận ra số tiền" reply. Declining is cheap; booking an
    expense the user never made is not — every rule below exists to make
    the wrong-amount outcome impossible rather than merely unlikely.
    """
    cleaned = (text or "").strip()
    if _looks_like_a_question(cleaned) or _looks_like_price_commentary(cleaned):
        return None

    candidates = [
        match
        for match in _AMOUNT_RE.finditer(cleaned)
        if not _is_ratio_token(cleaned, match)
    ]
    if not candidates:
        return None
    if any(_has_compound_tail(cleaned, match) for match in candidates):
        return None
    if any(_is_partial_number(cleaned, match) for match in candidates):
        return None

    if len(candidates) > 1:
        # Bare counts sit next to the real amount all the time — "2 ly
        # trà sữa 90k", "mua 2 áo 300k". A count is small, so dropping
        # sub-1k bare numbers separates quantity from money without
        # touching either candidate in "mua áo 300000 quần 200k" — that
        # one keeps both and is declined below. Filtering on the đơn vị
        # alone (the first cut) silently booked the 200k and threw the
        # 300k purchase away, which is worse than not capturing at all.
        candidates = [
            match
            for match in candidates
            if match.group(2) or _parse_amount_match(match) >= _MIN_PLAIN_AMOUNT
        ]
    if len(candidates) != 1:
        # Either nothing survived, or several real amounts compete — a
        # genuine multi-item message ("tiền xăng 50k, ăn trưa 50k"),
        # which is the batch path's job, not ours.
        return None

    match = candidates[0]
    amount = _parse_amount_match(match)
    if amount <= 0:
        return None
    has_unit = bool(match.group(2))
    if not has_unit and amount < _MIN_PLAIN_AMOUNT:
        return None

    merchant = _clean_merchant(f"{cleaned[:match.start()]} {cleaned[match.end():]}")
    if not merchant:
        return None

    return ParsedExpenseItem(
        amount=amount,
        merchant=merchant,
        category_hint=_guess_category(merchant),
    )


def _single_item_from_parsed(
    parsed: dict,
    *,
    fallback_text: str,
) -> ParsedExpenseItem | None:
    """Validate one ``parse_manual`` JSON reply into an item, or None."""
    if not parsed.get("is_expense"):
        return None
    try:
        amount = float(parsed.get("amount", 0))
    except (TypeError, ValueError):
        amount = 0.0
    if amount <= 0:
        return None
    merchant = parsed.get("merchant") or fallback_text
    return ParsedExpenseItem(
        amount=amount,
        merchant=merchant,
        category_hint=_guess_category(merchant),
    )


# "50.000" / "50,000" is Vietnamese thousands grouping, not a decimal —
# exactly three digits behind the separator is the tell. "1,5" and "1.5"
# are decimals ("1,5tr").
_GROUPED_NUMBER_RE = re.compile(r"\d{1,3}[.,]\d{3}")


def _read_number(raw_number: str) -> float:
    """Read one captured number, resolving the ``.``/``,`` ambiguity."""
    if _GROUPED_NUMBER_RE.fullmatch(raw_number):
        return float(raw_number.replace(",", "").replace(".", ""))
    return float(raw_number.replace(",", "."))


def _parse_amount_match(match: re.Match[str]) -> float:
    raw_number = match.group(1)
    suffix = (match.group(2) or "").lower()

    # Resolve the grouping BEFORE the multiplier, not after. Reading
    # "1.500k" as the decimal 1.5 made it 1.500đ instead of 1.500.000đ —
    # a 1000× error on a real rent payment — even though the very same
    # digits without the "k" were already handled correctly below.
    number = _read_number(raw_number)

    if suffix:
        if suffix == "k" or suffix in {"ngàn", "nghìn", "ngan", "nghin"}:
            return number * 1_000
        if suffix in {"tr", "triệu", "trieu"}:
            return number * 1_000_000

    # No suffix: small plain numbers stay as-is for rare exact-VND entries.
    return number


def _clean_merchant(text: str) -> str:
    merchant = re.sub(r"\s+", " ", text).strip(" ,-+;:")
    merchant = _LEADING_TIME_RE.sub("", merchant).strip(" ,-+;:")
    return merchant


def _guess_category(text: str | None) -> str:
    normalized = (text or "").lower()
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(keyword in normalized for keyword in keywords):
            return category
    # Confirmation flow is terminal — show "Khác" rather than blocking on
    # a clarifier the user can no longer reach.
    return "other"


def _coerce_parsed_items(
    items: list,
    *,
    fallback_text: str,
) -> list[ParsedExpenseItem]:
    parsed_items: list[ParsedExpenseItem] = []
    for raw_item in items:
        if not isinstance(raw_item, dict):
            continue
        try:
            amount = float(raw_item.get("amount", 0))
        except (TypeError, ValueError):
            amount = 0.0
        if amount <= 0:
            continue
        merchant = _clean_merchant(str(raw_item.get("merchant") or fallback_text))
        category_hint = str(
            raw_item.get("category_hint") or ""
        ).strip() or _guess_category(merchant)
        if category_hint == "other":
            category_hint = _guess_category(merchant)
        parsed_items.append(
            ParsedExpenseItem(
                amount=amount,
                merchant=merchant,
                category_hint=category_hint or "other",
            )
        )
    return parsed_items
