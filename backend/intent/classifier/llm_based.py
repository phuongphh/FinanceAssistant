"""LLM-based intent classifier — Layer 2 fallback.

Used when the rule-based classifier returns None or low confidence.
Targets ~25% of queries (~150 input tokens, ~50 output tokens) at
DeepSeek pricing — one-cent per ~120 calls. The pipeline only escalates
here when needed so the budget stays well under $5/month even at
1k queries/day.

Cache strategy
--------------
The prompt has no user-identifying context (only the raw query is
interpolated), so cache entries are shared across users via
``shared_cache=True``. Same query hashed → 1 LLM call total.

Failure mode
------------
On any exception (rate limit, timeout, invalid JSON) we return None so
the pipeline can fall back to the rule-based result or UNCLEAR. The
classifier never raises — analytics still see the failed call so cost +
error rate are observable.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.intent.intents import (
    CLASSIFIER_LLM,
    IntentResult,
    IntentType,
)
from backend.services.llm_service import LLMError, call_llm

logger = logging.getLogger(__name__)
settings = get_settings()


# DeepSeek pricing (USD per 1M tokens) — used to attribute cost to the
# ``llm_classifier_call`` analytics event. Pricing as of 2026-04. Update
# here when DeepSeek changes their rate card; the test for max-cost-per-
# call will catch silent drift.
_DEEPSEEK_INPUT_USD_PER_1M = 0.27
_DEEPSEEK_OUTPUT_USD_PER_1M = 1.10


# Single-source-of-truth prompt. Kept as a module constant (per the
# acceptance criteria) so ops can grep for it and tests can validate
# the intent enum stays in sync.
LLM_CLASSIFIER_PROMPT = """Bạn là intent classifier cho Bé Tiền — finance assistant cho người Việt.

Phân loại câu hỏi của user vào MỘT trong các intents sau:

INTENTS:
- query_assets: Hỏi về tài sản (BĐS, CK, crypto, vàng, tiền)
- query_net_worth: Hỏi tổng tài sản / net worth
- query_portfolio: Hỏi danh mục chứng khoán
- query_expenses: Hỏi chi tiêu chung
- query_expenses_by_category: Hỏi chi tiêu theo loại (ăn uống, sức khỏe...)
- query_income: Hỏi thu nhập / lương
- query_cashflow: Hỏi dòng tiền / dư cuối tháng
- query_market: Hỏi giá thị trường (VNM, BTC, VN-Index)
- query_goals: Hỏi mục tiêu của user
- query_goal_progress: Hỏi tiến độ mục tiêu cụ thể
- action_record_saving: Muốn ghi tiết kiệm
- action_quick_transaction: Muốn ghi giao dịch nhanh
- advisory: Hỏi lời khuyên đầu tư / tài chính
- planning: Hỏi cách lập kế hoạch
- greeting: Chào hỏi
- help: Cần hướng dẫn
- out_of_scope: Hoàn toàn ngoài tài chính (thời tiết, kể chuyện, kiến thức chung)

PARAMETERS (extract nếu có, không có thì bỏ qua):
- time_range: "today" | "yesterday" | "this_week" | "last_week" | "this_month" | "last_month" | "this_year"
- category: "food" | "transport" | "housing" | "shopping" | "health" | "education" | "entertainment" | "utility" | "gift" | "investment"
- asset_type: "cash" | "stock" | "real_estate" | "crypto" | "gold"
- ticker: viết hoa, ví dụ "VNM", "BTC", "VNINDEX"
- amount: số nguyên VND
- goal_name: tên mục tiêu

OUTPUT JSON ONLY (không thêm text khác):
{{"intent": "<intent_name>", "confidence": <0.0-1.0>, "parameters": {{}}}}

USER QUERY: {query}

JSON:"""


@dataclass(frozen=True)
class LLMCallStats:
    """Stats from one classify call — surfaced via ``last_call_stats``
    so the pipeline / analytics layer can attribute cost without
    re-parsing the response.
    """
    input_tokens: int
    output_tokens: int
    latency_ms: int
    cost_usd: float
    cache_hit: bool


class LLMClassifier:
    """DeepSeek-backed intent classifier.

    Constructor accepts a ``db_factory`` callable so tests can inject a
    fake session factory. In production we use the global engine via
    ``get_session_factory()``.
    """

    def __init__(
        self,
        db_factory=None,
        *,
        cache_ttl_days: int = 1,
    ) -> None:
        self._db_factory = db_factory
        self._cache_ttl_days = cache_ttl_days
        self.last_call_stats: LLMCallStats | None = None

    async def classify(self, text: str) -> IntentResult | None:
        if not text or not text.strip():
            return None

        prompt = LLM_CLASSIFIER_PROMPT.format(query=text.strip())
        started = time.perf_counter()

        # ``call_llm`` already implements the cache-key + 30-day TTL +
        # tokens accounting. We use ``shared_cache=True`` because the
        # prompt only contains the user's raw text, never user-specific
        # state, so one cached entry serves everyone.
        async with self._open_session() as db:
            try:
                raw = await call_llm(
                    prompt,
                    task_type="intent_classify",
                    db=db,
                    shared_cache=True,
                    use_cache=True,
                )
                if db is not None:
                    await db.commit()
            except LLMError:
                logger.warning("LLM intent classifier call failed", exc_info=True)
                return None
            except Exception:
                logger.exception("LLM intent classifier crashed")
                return None

        latency_ms = int((time.perf_counter() - started) * 1000)

        result = self._parse_response(raw, text)
        if result is None:
            return None

        # ``call_llm`` doesn't expose token usage on cache hits, so we
        # estimate post-hoc from the prompt + response when not given.
        # Cache hits cost $0 — that's the whole point of the layer.
        stats = self._build_stats(prompt, raw, latency_ms, cache_hit=False)
        self.last_call_stats = stats
        return result

    # -------------------- internals --------------------

    def _open_session(self):
        """Return an async-context-managed session.

        Uses an injected factory in tests; falls back to the real
        session factory in production. If neither is available (e.g.
        DATABASE_URL unset in CI), yields ``None`` and the cache step
        is skipped — the LLM call still works, just uncached.
        """
        from contextlib import asynccontextmanager

        if self._db_factory is not None:
            factory = self._db_factory
        else:
            try:
                from backend.database import get_session_factory
                factory = get_session_factory()
            except Exception:
                factory = None

        @asynccontextmanager
        async def _ctx():
            if factory is None:
                yield None
                return
            async with factory() as session:
                yield session

        return _ctx()

    def _parse_response(self, raw: str, original: str) -> IntentResult | None:
        # Strip code fences just in case the model wraps the JSON.
        cleaned = "\n".join(
            line for line in raw.splitlines() if not line.startswith("```")
        ).strip()
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("LLM returned non-JSON response: %r", raw[:200])
            return None

        intent_str = str(data.get("intent", "")).strip()
        try:
            intent = IntentType(intent_str)
        except ValueError:
            logger.info(
                "LLM returned unknown intent %r — treating as unclear", intent_str
            )
            intent = IntentType.UNCLEAR

        try:
            confidence = float(data.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))

        parameters = data.get("parameters") or {}
        if not isinstance(parameters, dict):
            parameters = {}

        # Normalise ticker capitalisation — the dispatcher / market
        # handler expect uppercase.
        if isinstance(parameters.get("ticker"), str):
            parameters["ticker"] = parameters["ticker"].upper()

        return IntentResult(
            intent=intent,
            confidence=confidence,
            parameters=parameters,
            raw_text=original,
            classifier_used=CLASSIFIER_LLM,
        )

    def _build_stats(
        self,
        prompt: str,
        response: str,
        latency_ms: int,
        *,
        cache_hit: bool,
    ) -> LLMCallStats:
        # Rough token approximation — DeepSeek doesn't return exact
        # tokens for cache hits and we don't always have access to the
        # raw API response object here. ~4 chars/token works well for
        # Vietnamese mixed-script text in practice.
        input_tokens = max(1, len(prompt) // 4)
        output_tokens = max(1, len(response) // 4)
        cost = (
            input_tokens * _DEEPSEEK_INPUT_USD_PER_1M / 1_000_000
            + output_tokens * _DEEPSEEK_OUTPUT_USD_PER_1M / 1_000_000
        )
        if cache_hit:
            cost = 0.0
        return LLMCallStats(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            cost_usd=cost,
            cache_hit=cache_hit,
        )


__all__ = ["LLMClassifier", "LLM_CLASSIFIER_PROMPT", "LLMCallStats"]
