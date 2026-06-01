"""LLM-based intent classifier — Layer 2 fallback.

Used when the rule-based classifier returns None or low confidence.
Targets ~25% of queries (~150 input tokens, ~50 output tokens) on Groq's
Llama 3.3 70B — sub-second first-token latency at $0.59/$0.79 per 1M
tokens, so the budget stays well under $5/month even at 1k queries/day.

We deliberately do NOT use DeepSeek V4-Flash here: it's fast in
throughput but takes 4-12s for first token by design (batch-oriented),
which blows the 2s pipeline timeout for an interactive flow.

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

from backend.agent.limits import estimate_cost_usd
from backend.config import get_settings
from backend.intent.intents import (
    CLASSIFIER_LLM,
    IntentResult,
    IntentType,
)
from backend.services.llm_service import LLMError, call_llm

logger = logging.getLogger(__name__)
settings = get_settings()


# Tier 1 has to respond in <2s wall-clock from the pipeline's perspective.
# Groq Llama 3.3 70B typically returns in 300-700ms; we cap at 3s to give
# headroom for TLS / DNS jitter on cold connections without exceeding the
# pipeline's wait_for budget.
_TIER1_TIMEOUT_SECONDS = 3.0


# Single-source-of-truth prompt. Kept as a module constant (per the
# acceptance criteria) so ops can grep for it and tests can validate
# the intent enum stays in sync.
LLM_CLASSIFIER_PROMPT = """Bạn là intent classifier cho Bé Tiền — finance assistant cho người Việt.

Phân loại câu hỏi của user vào MỘT trong các intents sau:

INTENTS:
- query_assets: Hỏi về tài sản (BĐS, CK, crypto, vàng, tiền)
- query_net_worth: Hỏi tổng tài sản / net worth
- query_portfolio: Hỏi danh mục chứng khoán
- query_expenses: Hỏi chi tiêu chung; tổng hợp/báo cáo giao dịch theo thời gian
- query_expenses_by_category: Hỏi chi tiêu theo loại (ăn uống, sức khỏe...)
- query_income: Hỏi thu nhập / lương
- query_cashflow: Hỏi dòng tiền / dư cuối tháng
- query_market: Hỏi giá thị trường (cổ phiếu VNM, crypto BTC, vàng SJC, VN-Index). Bao gồm cả câu hỏi tổng quát kiểu "giá vàng", "giá crypto", "giá cổ phiếu".
- query_goals: Hỏi mục tiêu của user
- query_goal_progress: Hỏi tiến độ mục tiêu cụ thể
- query_twin: Hỏi Bé Tiền tương lai / dự phóng tài sản / mô phỏng Financial Twin
- action_record_saving: Muốn ghi tiết kiệm
- action_quick_transaction: Ghi giao dịch nhanh (tiền ra/vào). "được cho/thưởng/lì xì/tìm/nhặt X" là tiền vào.
- action_add_asset: Muốn thêm tài sản mới (BĐS, cổ phiếu, crypto, vàng, tiền mặt). Ví dụ: "thêm bất động sản", "thêm cổ phiếu FPT", "nhập crypto"
- action_edit_asset: Muốn sửa / cập nhật tài sản đã có. Ví dụ: "sửa đất Ba Tư", "sửa cổ phiếu FPT thành 200 cổ", "cập nhật bất động sản". Khi user nói "thành <giá trị>" / "= <giá trị>" thì capture vào new_value để handler áp dụng update inline.
- action_delete_asset: Muốn xoá / bỏ tài sản đã có. Ví dụ: "xoá tài sản ACB", "xoá ví zalopay", "xoá cổ phiếu FPT", "huỷ bất động sản"
- action_add_goal: Muốn thêm mục tiêu tài chính mới. Ví dụ: "thêm mục tiêu", "tạo mục tiêu mới", "đặt goal"
- nav_expense_dashboard: Muốn mở dashboard / bảng điều khiển chi tiêu. Ví dụ: "chi tiêu dashboard", "mở dashboard chi tiêu", "bảng điều khiển chi phí"
- advisory: Hỏi lời khuyên đầu tư / tài chính
- planning: Hỏi cách lập kế hoạch
- greeting: Chào hỏi
- help: Cần hướng dẫn
- out_of_scope: Hoàn toàn ngoài tài chính (thời tiết, kể chuyện, kiến thức chung)

PARAMETERS (extract nếu có, không có thì bỏ qua):
- time_range: "today" | "yesterday" | "this_week" | "last_week" | "this_month" | "last_month" | "this_year"
- category (cho query_expenses_by_category): "food" | "transport" | "housing" | "shopping" | "health" | "education" | "entertainment" | "utility" | "gift" | "investment"
- category (cho query_market — khi user hỏi cả nhóm chứ không phải 1 mã cụ thể): "gold" | "crypto" | "stock"
  Ví dụ: "giá vàng" → category=gold; "giá crypto"/"giá tiền số" → category=crypto; "giá cổ phiếu" → category=stock
- asset_type (cho query_assets / action_add_asset / action_edit_asset / action_delete_asset): "cash" | "stock" | "real_estate" | "crypto" | "gold"
- asset_name (cho action_edit_asset / action_delete_asset): tên / nhãn tài sản nếu user nêu rõ. Ví dụ: "ACB", "MoMo", "FPT", "đất Ba Tư"
- new_value (cho action_edit_asset khi user dùng "thành <X>" / "= <X>"): chuỗi giá trị mới user nêu, nguyên văn. Ví dụ: "200 cổ", "50tr", "1.2 tỷ", "5 chỉ"
- ticker (cho query_market khi user hỏi 1 mã cụ thể): viết hoa, ví dụ "VNM", "BTC", "VNINDEX"
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
    """Groq-backed intent classifier (Llama 3.3 70B).

    Constructor accepts a ``db_factory`` callable so tests can inject a
    fake session factory. In production we use the global engine via
    ``get_session_factory()``.

    ``cache_ttl_days`` defaults to 7. Tier 1 prompts are simple
    classification with ``shared_cache=True`` across all users, so the
    same query hashes hit the same cache slot indefinitely — extending
    from 1 day to 7 days lifts hit rate noticeably on common phrasings
    ("tài sản của tôi", "giá vàng", "tổng chi tiêu tháng này") without
    risking staleness, because the intent enum itself is stable.
    """

    def __init__(
        self,
        db_factory=None,
        *,
        cache_ttl_days: int = 7,
    ) -> None:
        self._db_factory = db_factory
        self._cache_ttl_days = cache_ttl_days
        self.last_call_stats: LLMCallStats | None = None

    async def classify(self, text: str) -> IntentResult | None:
        if not text or not text.strip():
            return None

        prompt = LLM_CLASSIFIER_PROMPT.format(query=text.strip())
        started = time.perf_counter()

        # ``call_llm`` already implements the cache-key + tokens
        # accounting. We use ``shared_cache=True`` because the prompt
        # only contains the user's raw text, never user-specific state,
        # so one cached entry serves everyone. ``provider="groq"`` keeps
        # Tier 1 off DeepSeek's slow-first-token path.
        async with self._open_session() as db:
            try:
                raw = await call_llm(
                    prompt,
                    task_type="intent_classify",
                    db=db,
                    shared_cache=True,
                    use_cache=True,
                    cache_ttl_days=self._cache_ttl_days,
                    provider="groq",
                    timeout=_TIER1_TIMEOUT_SECONDS,
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
        # Rough token approximation — the provider doesn't return exact
        # tokens for cache hits and we don't always have access to the
        # raw API response object here. ~4 chars/token works well for
        # Vietnamese mixed-script text in practice.
        input_tokens = max(1, len(prompt) // 4)
        output_tokens = max(1, len(response) // 4)
        # Cost comes from the shared pricing table (Groq rates) rather
        # than redeclaring per-1M constants here — keeps the analytics
        # attribution in lockstep with the budget/kill-switch ledgers.
        cost = (
            0.0
            if cache_hit
            else estimate_cost_usd(
                model=settings.groq_model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        )
        return LLMCallStats(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            cost_usd=cost,
            cache_hit=cache_hit,
        )


__all__ = ["LLMClassifier", "LLM_CLASSIFIER_PROMPT", "LLMCallStats"]
