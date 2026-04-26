"""LLM prompt + extractor for the storytelling expense capture feature.

Phase 3A pivots from "track every transaction" to "user kể chuyện về
chi tiêu lớn". This module owns the LLM half of that flow:

- ``STORYTELLING_PROMPT``: the actual prompt template, with a
  ``{threshold}`` placeholder so the LLM ignores spend below the
  user's income-derived micro-threshold.
- ``extract_transactions_from_story()``: thin wrapper around the
  ``llm_service.call_llm`` cached client. Returns a structured dict
  the handler turns into a confirmation message.

Output schema is documented at the top of the prompt and re-validated
in Python after the JSON parse, because DeepSeek occasionally adds
extra fields and the handler downstream is intolerant of them.

Cost & caching
--------------
- ``call_llm`` keys on ``(task_type, user_id, prompt_hash)`` so two
  users telling the same story still get separate cache entries (the
  threshold differs and we don't want cross-user leakage anyway).
- ``use_cache=True`` is the default — identical stories from the same
  user (e.g. "test test test" during dev) reuse the cached response.

Typical cost per call on DeepSeek: ~$0.001 (1500 max output tokens,
prompt ~600 tokens). Test suite of 30+ stories costs ~$0.03 total —
cheap enough to run on every prompt iteration.
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.llm_service import LLMError, call_llm

logger = logging.getLogger(__name__)


# Valid category codes — kept in sync with backend.config.categories
# (storytelling supports a slightly narrower set since "transfer" /
# "saving" don't fit the "story about something I bought" frame).
VALID_CATEGORIES = frozenset(
    {
        "food",
        "transport",
        "housing",
        "shopping",
        "health",
        "education",
        "entertainment",
        "investment",
        "gift",
        "utility",
        "other",
    }
)


STORYTELLING_PROMPT = """Bạn là AI finance assistant cho người Việt. User vừa kể về chi tiêu của họ trong vài ngày qua.

NHIỆM VỤ: Trích xuất MỌI giao dịch đáng kể (>= {threshold} VND) thành JSON.

QUY TẮC QUAN TRỌNG:
1. CHỈ extract giao dịch >= {threshold} VND. Giao dịch nhỏ hơn → đưa vào "ignored_small", KHÔNG đưa vào "transactions".
2. Nếu user nói chia tiền (vd: "ăn với bạn 400k chia đôi") → chỉ tính phần của user (200k).
3. Nếu user không rõ số tiền → đưa vào "needs_clarification", KHÔNG đoán.
4. Nếu user chỉ kể chuyện không có chi tiêu → trả về transactions: [].
5. Số tiền không được âm. Nếu user nói "được 5tr" (thu nhập) → bỏ qua, không phải chi tiêu.
6. Đơn vị tiền VN:
   - "k" hoặc "ngàn"/"nghìn" = × 1.000   (50k = 50.000đ)
   - "tr" hoặc "triệu" = × 1.000.000     (5tr = 5.000.000đ)
   - "tỷ"/"ty" = × 1.000.000.000

CATEGORIES (chọn một):
- food: nhà hàng, gọi đồ ăn lớn, ăn uống cho event
- transport: Grab/taxi đường xa, xăng, vé máy bay, vé tàu
- housing: tiền nhà, sửa chữa, đồ dùng gia đình lớn
- shopping: quần áo, đồ điện tử, mỹ phẩm
- health: thuốc, viện phí, gym, spa
- education: học phí, sách, khoá học
- entertainment: du lịch, xem phim, concert, game
- investment: mua thêm cổ phiếu, crypto, vàng
- gift: quà tặng, mừng sự kiện, lì xì
- utility: điện, nước, internet, bảo hiểm
- other: không rõ

OUTPUT — TRẢ VỀ JSON DUY NHẤT (không thêm text giải thích):
{{
  "transactions": [
    {{
      "amount": 800000,
      "merchant": "nhà hàng Ngon",
      "category": "food",
      "time_hint": "tối qua",
      "confidence": 0.9
    }}
  ],
  "needs_clarification": [
    {{"text": "mua đồ", "reason": "không rõ mua gì và bao nhiêu tiền"}}
  ],
  "ignored_small": [
    {{"text": "ăn phở 50k", "amount": 50000, "reason": "dưới threshold {threshold}"}}
  ]
}}

User threshold: {threshold} VND.
Câu chuyện của user:
\"\"\"{story}\"\"\""""


@dataclass
class StorytellingResult:
    """Structured output from the LLM extractor.

    Always contains all three lists (possibly empty) — the handler can
    iterate without ``.get()`` defensiveness. ``raw`` is the original
    LLM payload, kept for logging / debugging.
    """
    transactions: list[dict[str, Any]] = field(default_factory=list)
    needs_clarification: list[dict[str, Any]] = field(default_factory=list)
    ignored_small: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def has_anything(self) -> bool:
        """True if there's something to show the user (anything but a no-op)."""
        return bool(
            self.transactions
            or self.needs_clarification
            or self.ignored_small
        )


def _coerce_amount(value: Any) -> int | None:
    """Best-effort conversion of LLM amount field to a positive int VND.

    DeepSeek occasionally returns amounts as strings ("800000") or
    floats. We accept both, reject negatives, and reject zero (a zero
    amount would have been ignored by the prompt anyway).
    """
    try:
        amt = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    if amt <= 0:
        return None
    return amt


def _validate_transaction(tx: dict[str, Any], threshold: int) -> dict[str, Any] | None:
    """Sanitise one LLM-emitted transaction.

    Drops it (returns None) if:
    - amount missing / non-numeric / non-positive
    - amount below threshold (LLM disobeyed — defence-in-depth)
    - category invalid → coerce to "other"
    """
    amount = _coerce_amount(tx.get("amount"))
    if amount is None or amount < threshold:
        return None

    category = (tx.get("category") or "other").strip().lower()
    if category not in VALID_CATEGORIES:
        category = "other"

    merchant = (tx.get("merchant") or "").strip()
    if not merchant:
        merchant = "Chi tiêu"

    confidence = tx.get("confidence")
    try:
        confidence = float(confidence) if confidence is not None else 0.7
    except (TypeError, ValueError):
        confidence = 0.7
    confidence = max(0.0, min(1.0, confidence))

    out: dict[str, Any] = {
        "amount": amount,
        "merchant": merchant[:200],
        "category": category,
        "confidence": confidence,
    }
    if tx.get("time_hint"):
        out["time_hint"] = str(tx["time_hint"])[:60]
    if tx.get("context"):
        out["context"] = str(tx["context"])[:200]
    return out


def parse_storytelling_response(
    raw: str | dict, *, threshold: int
) -> StorytellingResult:
    """Parse + validate LLM JSON output. Tolerates fenced code blocks.

    Pulled out as a pure function so the test suite can iterate on
    prompt outputs without making LLM calls.
    """
    if isinstance(raw, dict):
        data = raw
    else:
        text = (raw or "").strip()
        # Strip markdown fences (```json ... ```), which DeepSeek
        # occasionally emits despite ``response_format=json_object``.
        if text.startswith("```"):
            lines = [ln for ln in text.splitlines() if not ln.startswith("```")]
            text = "\n".join(lines).strip()
        try:
            data = json.loads(text) if text else {}
        except json.JSONDecodeError:
            logger.warning("storytelling: LLM returned non-JSON payload: %r", text[:200])
            return StorytellingResult(raw={"_error": "json_decode", "_text": text[:500]})

    if not isinstance(data, dict):
        return StorytellingResult(raw={"_error": "not_a_dict"})

    txs_raw = data.get("transactions") or []
    txs: list[dict[str, Any]] = []
    if isinstance(txs_raw, list):
        for tx in txs_raw:
            if not isinstance(tx, dict):
                continue
            cleaned = _validate_transaction(tx, threshold=threshold)
            if cleaned is not None:
                txs.append(cleaned)

    needs = data.get("needs_clarification") or []
    if not isinstance(needs, list):
        needs = []
    needs = [
        item for item in needs if isinstance(item, dict)
    ]

    ignored = data.get("ignored_small") or []
    if not isinstance(ignored, list):
        ignored = []
    ignored = [item for item in ignored if isinstance(item, dict)]

    return StorytellingResult(
        transactions=txs,
        needs_clarification=needs,
        ignored_small=ignored,
        raw=data,
    )


async def extract_transactions_from_story(
    story: str,
    *,
    threshold: int = 200_000,
    db: AsyncSession | None = None,
    user_id: uuid.UUID | None = None,
) -> StorytellingResult:
    """Run the LLM extractor over ``story`` and return a structured result.

    Falls back to an empty ``StorytellingResult`` (no transactions)
    when the LLM fails or returns garbage — the handler then shows the
    user a warm "thử lại nhé" prompt instead of crashing.

    ``user_id`` is required when ``db`` is provided so the cache is
    scoped per-user (storytelling output reflects the user's
    threshold + private spending narrative — never cross-share).
    """
    story = (story or "").strip()
    if not story:
        return StorytellingResult()

    if threshold < 0:
        threshold = 0
    threshold_int = int(threshold)

    prompt = STORYTELLING_PROMPT.format(threshold=threshold_int, story=story)

    try:
        raw = await call_llm(
            prompt,
            task_type="storytelling_extract",
            db=db,
            user_id=user_id,
            use_cache=db is not None,
        )
    except LLMError:
        logger.warning("storytelling: LLM call failed — returning empty result")
        return StorytellingResult()
    except Exception:  # noqa: BLE001 — never propagate to the user
        logger.exception("storytelling: unexpected error from LLM")
        return StorytellingResult()

    result = parse_storytelling_response(raw, threshold=threshold_int)
    logger.info(
        "storytelling: extracted txs=%d clarif=%d ignored=%d",
        len(result.transactions),
        len(result.needs_clarification),
        len(result.ignored_small),
    )
    return result
