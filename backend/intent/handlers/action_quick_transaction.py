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
from backend.intent.clarifier import build_message_from_key
from backend.intent.handlers.base import IntentHandler
from backend.intent.intents import IntentResult
from backend.models.user import User
from backend.schemas.expense import ExpenseCreate
from backend.services import expense_service
from backend.services.expense_source_resolver import apply_default_source
from backend.services.llm_service import call_llm

logger = logging.getLogger(__name__)


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


_AMOUNT_RE = re.compile(
    r"(?<!\w)(\d+(?:[.,]\d+)?)(?:\s*(k|K|ngàn|nghìn|ngan|nghin|tr|triệu|trieu))?",
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


# Wallet top-up shape: "thêm/cộng/nạp/nhận X vào ví|tài khoản Y" —
# the user is explicitly moving money INTO a wallet/account, which is
# income from the cash-flow perspective. Without this guard the
# verbs (thêm, cộng, nạp) flow through the expense recorder because
# they're not in _INCOME_KEYWORDS — silently corrupting expense
# history (caught by code review on PR #669).
_WALLET_TOPUP_RE = re.compile(
    r"^\s*(?:them|cong|nap|nhan|cho|gui|bo|duoc|nop)\s+[+\-]?\s*[\d.,]+"
    r".*?\b(?:vao|into|toi|den)\s+"
    r"(?:vi|tai\s*khoan|cash|tien\s*mat|momo|zalopay|viettel|"
    r"vcb|acb|tcb|mb|tpb|techcom|sacombank|bidv|vietinbank)\b",
    re.IGNORECASE,
)


def _looks_like_wallet_topup(text: str) -> bool:
    """True when the message reads as a wallet/account top-up.

    Distinct from generic income (no salary verb) but still income from
    the expense-recorder's perspective — recording these as expenses
    inverts cash flow on the user's books.
    """
    if not text:
        return False
    return bool(_WALLET_TOPUP_RE.search(_strip_diacritics(text.lower())))


# Verbs that indicate the user is receiving money (income), NOT spending.
# Detected on the diacritic-stripped lowercased text to be tolerant of
# typos. If any of these match, the handler bails before recording an
# expense — see issues #656, #661.
_INCOME_KEYWORDS: tuple[str, ...] = (
    "nhan luong",
    "nhan thuong",
    "nhan tien",
    "luong",
    # NOTE: bare "thuong" is intentionally OMITTED — after diacritic
    # stripping it collides with the common adverb "thường" (usually,
    # often), which would swallow ordinary expenses like
    # "thường ăn sáng 50k". Only phrasal forms are listed.
    "thuong tet",
    "tien thuong",
    "duoc thuong",
    "duoc tang",
    "duoc cho",
    "thu nhap",
    "kiem duoc",
    "ban duoc",
    "hoan tien",
    "lai ngan hang",
    "co tuc",
    "freelance",
    "lam them",
)

# Verbs that explicitly mean "spend" — used to override the income check
# in mixed sentences like "lương tháng này tiêu hết 5tr" (expense wins).
# NOTE: bare "tra" is intentionally OMITTED — it is a substring of
# "tra luong" / "tra thuong" (paying salary/bonus, which is income from
# the user's perspective), so including it would break "công ty trả
# lương 20tr". The phrasal "tra tien" still covers genuine spending.
_EXPENSE_KEYWORDS: tuple[str, ...] = (
    "tieu",
    "chi tieu",
    "tra tien",
    "mua",
    "thanh toan",
    "bo tien",
    "het",
)


def _strip_diacritics(text: str) -> str:
    import unicodedata

    return "".join(
        ch
        for ch in unicodedata.normalize("NFD", text)
        if unicodedata.category(ch) != "Mn"
    ).replace("đ", "d").replace("Đ", "D")


def _has_leading_plus_sign(text: str) -> bool:
    """True if the message starts with an explicit ``+`` before a number.

    Convention: a leading ``+`` is the user's most direct signal that
    this is money-in, not expense. The fast-path in ``message.py``
    normally catches these before they reach the intent classifier; this
    is a belt-and-suspenders check so signed input is never silently
    recorded as expense even if routing changes.
    """
    return bool(re.match(r"^\s*\+\s*\d", text or ""))


def _looks_like_income(text: str) -> bool:
    """True if the message reads as income rather than expense.

    Used as a pre-check in the expense handler to avoid mis-recording
    "nhận lương 20tr vào tiền mặt" as an expense (#656). If the message
    contains BOTH income and expense verbs, expense wins — the user is
    describing what they did with the money, not the receipt itself.

    Also fires when the message starts with an explicit ``+`` sign so
    "+200k" never gets recorded as an expense.
    """
    if not text:
        return False
    if _has_leading_plus_sign(text):
        return True
    # Explicit wallet top-ups ("thêm 3tr vào ví momo") are always
    # income, regardless of which verb leads. Check before the
    # keyword/expense balancing because the topup phrasing is
    # unambiguous — there is no "thêm 3tr vào ví momo để tiêu" reading
    # that makes the money flow OUT.
    if _looks_like_wallet_topup(text):
        return True
    norm = _strip_diacritics(text.lower())
    has_income = any(kw in norm for kw in _INCOME_KEYWORDS)
    if not has_income:
        return False
    has_expense = any(kw in norm for kw in _EXPENSE_KEYWORDS)
    return not has_expense


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

        items = await self._extract_items(text, params, db, user)
        if not items:
            return _FALLBACK_REPLY

        if len(items) == 1:
            item = items[0]
            expense_data = ExpenseCreate(
                amount=float(item.amount),
                merchant=item.merchant or text,
                category=item.category_hint,
                note=text,
                source="manual",
                expense_date=date.today(),
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
                    merchant=item.merchant or text,
                    category=item.category_hint,
                    note=text,
                    source="manual",
                    expense_date=date.today(),
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
        return [single_item] if single_item else []

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
        try:
            raw = await call_llm(
                _SINGLE_PARSE_PROMPT.format(text=text),
                task_type="parse_manual",
                db=db,
                user_id=user.id,
                use_cache=True,
                shared_cache=False,
                provider="groq",
                timeout=5.0,
            )
            parsed = _load_json_response(raw)
        except Exception:
            logger.exception("Quick-transaction LLM parse failed for %r", text)
            return None

        if not parsed.get("is_expense"):
            return None
        try:
            parsed_amount = float(parsed.get("amount", 0))
        except (TypeError, ValueError):
            parsed_amount = 0.0
        if parsed_amount <= 0:
            return None
        parsed_merchant = parsed.get("merchant") or text
        return ParsedExpenseItem(
            amount=parsed_amount,
            merchant=parsed_merchant,
            category_hint=_guess_category(parsed_merchant),
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


def _parse_amount_match(match: re.Match[str]) -> float:
    raw_number = match.group(1)
    suffix = (match.group(2) or "").lower()

    if suffix:
        number = float(raw_number.replace(",", "."))
        if suffix == "k" or suffix in {"ngàn", "nghìn", "ngan", "nghin"}:
            return number * 1_000
        if suffix in {"tr", "triệu", "trieu"}:
            return number * 1_000_000

    # No suffix: treat 50,000 / 50.000 as thousands separators; keep
    # small plain numbers as-is for rare exact-VND entries.
    if re.fullmatch(r"\d{1,3}([.,])\d{3}", raw_number):
        return float(raw_number.replace(",", "").replace(".", ""))
    return float(raw_number.replace(",", "."))


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
