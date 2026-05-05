"""Phase 3.7 Orchestrator — routes a query to the right tier.

Three tiers:

- **Tier 1** (Phase 3.5): rule + LLM intent classifier → handlers.
  Cheapest path; handles "tài sản của tôi", "VNM giá bao nhiêu",
  greetings, etc.
- **Tier 2** (Epic 1): DeepSeek function calling → typed tools.
  Handles filter / sort / aggregate / compare.
- **Tier 3** (Epic 2): Claude Sonnet multi-step reasoning + streaming.
  Handles advisory / what-if / planning.

Routing strategy (cost-aware cascade):

1. Heuristic pre-classify by regex keywords (free, instant). A clear
   tier-3 signal goes straight to Tier 3; a clear tier-2 signal goes
   straight to Tier 2.
2. Ambiguous queries cascade: try Tier 1 first; escalate if intent
   is UNCLEAR or confidence < threshold.
3. Tier 3 calls always pass through rate-limit + cost-kill-switch
   gates. If rate-limited we degrade to Tier 2; if the cost gate
   trips we return a graceful "đợi một lát nhé" message.

Why a hand-written cascade rather than letting an LLM "router"
choose: the spec calls for cost <$0.001/query average, which is
incompatible with running an LLM on every routing decision. Regex
heuristics handle ~85% correctly and the cascade catches the rest.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent.rate_limit import (
    DailyCostTracker,
    RateLimiter,
    get_cost_tracker,
    get_rate_limiter,
)
from backend.agent.streaming.base import Streamer
from backend.agent.tier2.db_agent import DBAgent, DBAgentResult
from backend.agent.tier2.formatters import format_db_agent_response
from backend.agent.tier3.reasoning_agent import ReasoningAgent, ReasoningTrace
from backend.agent.tools import build_default_registry
from backend.agent.tools.base import ToolRegistry
from backend.intent.classifier.pipeline import IntentPipeline
from backend.intent.dispatcher import (
    DispatchOutcome,
    IntentDispatcher,
    OUTCOME_UNCLEAR,
)
from backend.intent.intents import IntentType
from backend.models.user import User

logger = logging.getLogger(__name__)

TIER_1 = "tier1"
TIER_2 = "tier2"
TIER_3 = "tier3"
AMBIGUOUS = "ambiguous"

# Re-classify with the LLM intent layer when rule-based confidence is
# below this. Same value Phase 3.5 dispatcher uses (HIGH_CONFIDENCE_THRESHOLD).
TIER1_CONFIDENCE_THRESHOLD = 0.8

_HEURISTICS_PATH = (
    Path(__file__).resolve().parents[2] / "content" / "router_heuristics.yaml"
)


@dataclass
class RouteResult:
    """What the orchestrator did. Returned to the caller for analytics
    + so the bot handler knows whether output went through the streamer
    (Tier 3) or arrived as plain text (Tier 1/2)."""

    tier: str
    routing_reason: str
    text: str | None = None  # Plain text reply (Tier 1/2). None for Tier 3.
    streamed: bool = False
    intent: IntentType | None = None
    confidence: float | None = None
    db_agent_result: DBAgentResult | None = None
    reasoning_trace: ReasoningTrace | None = None
    rate_limited: bool = False


class Orchestrator:
    """Top-level entry point — replaces the direct
    ``IntentPipeline.classify → IntentDispatcher.dispatch`` call in
    ``free_form_text.classify_and_dispatch``.

    Construction is lazy: tier-2 / tier-3 agents only build their LLM
    clients on first use. Cheap to instantiate per request OR once at
    import time."""

    def __init__(
        self,
        *,
        registry: ToolRegistry | None = None,
        intent_pipeline: IntentPipeline | None = None,
        intent_dispatcher: IntentDispatcher | None = None,
        db_agent: DBAgent | None = None,
        reasoning_agent: ReasoningAgent | None = None,
        rate_limiter: RateLimiter | None = None,
        cost_tracker: DailyCostTracker | None = None,
        heuristics_path: Path | None = None,
    ) -> None:
        self.registry = registry or build_default_registry()
        self.intent_pipeline = intent_pipeline or IntentPipeline()
        self.intent_dispatcher = intent_dispatcher or IntentDispatcher()
        self.db_agent = db_agent or DBAgent(self.registry)
        self.reasoning_agent = reasoning_agent or ReasoningAgent(self.registry)
        self.rate_limiter = rate_limiter or get_rate_limiter()
        self.cost_tracker = cost_tracker or get_cost_tracker()
        self.heuristics = self._load_heuristics(
            heuristics_path or _HEURISTICS_PATH
        )

    # ------------------------------------------------------------------
    # public
    # ------------------------------------------------------------------

    async def route(
        self,
        query: str,
        user: User,
        db: AsyncSession,
        *,
        streamer: Streamer | None = None,
    ) -> RouteResult:
        """Route ``query`` to the appropriate tier and return the result.

        ``streamer`` is required for Tier 3 — a Tier 3 query without
        a streamer would silently lose its reasoning output. We
        still allow it (returning ``text=None``) so callers like
        unit tests can use a fake streamer if they want one. If the
        query routes to Tier 1/2, the streamer is ignored and the
        response comes back via ``text``.
        """
        # Global cost gate. Hit before any LLM dispatch so a runaway
        # day stays bounded.
        if not await self.cost_tracker.can_spend():
            return RouteResult(
                tier="kill_switch",
                routing_reason="daily_cost_hard_limit",
                text=(
                    "Mình đang nghỉ một lát để cân đối chi phí. "
                    "Bạn quay lại sau vài giờ nữa nhé 🙏"
                ),
            )

        # Total per-user rate gate (cheap; same for any tier).
        total_decision = await self.rate_limiter.check_total(user.id)
        if not total_decision.allowed:
            return RouteResult(
                tier="rate_limited",
                routing_reason=total_decision.reason or "rate_limit_total",
                text=self._rate_limited_message(total_decision.retry_after_seconds),
                rate_limited=True,
            )

        tier_hint = self._heuristic_classify(query)

        if tier_hint == TIER_3:
            return await self._handle_tier3(
                query, user, db, streamer, reason="heuristic_tier3"
            )
        if tier_hint == TIER_2:
            return await self._cascade_tier2_then_3(
                query, user, db, streamer, reason="heuristic_tier2"
            )

        # Ambiguous — try Tier 1 first.
        return await self._cascade_tier1_then_up(
            query, user, db, streamer, reason="cascade"
        )

    # ------------------------------------------------------------------
    # heuristic classification
    # ------------------------------------------------------------------

    def _heuristic_classify(self, query: str) -> str:
        """Return ``TIER_2``, ``TIER_3``, or ``AMBIGUOUS``.

        Tier 3 wins on ANY signal because reasoning verbs are rare
        and high-confidence ("có nên", "làm thế nào để" never appear
        in a simple lookup). Tier 2 needs at least one signal too,
        but its keywords overlap with regular queries more (e.g.
        "tổng" appears in "tổng giám đốc"), so we still let the
        cascade rescue mis-routes.
        """
        text = (query or "").lower()
        tier3 = self._count_signals(text, self.heuristics.get("tier3_signals", {}))
        tier2 = self._count_signals(text, self.heuristics.get("tier2_signals", {}))

        if tier3 >= 1:
            return TIER_3
        if tier2 >= 1:
            return TIER_2
        return AMBIGUOUS

    @staticmethod
    def _count_signals(text: str, signals: dict[str, list[str]]) -> int:
        count = 0
        for patterns in signals.values():
            for pattern in patterns:
                try:
                    if re.search(pattern, text, flags=re.IGNORECASE):
                        count += 1
                except re.error as e:
                    logger.warning("Bad heuristic regex %r: %s", pattern, e)
        return count

    # ------------------------------------------------------------------
    # Cascade implementations
    # ------------------------------------------------------------------

    async def _cascade_tier1_then_up(
        self,
        query: str,
        user: User,
        db: AsyncSession,
        streamer: Streamer | None,
        reason: str,
    ) -> RouteResult:
        """Try Tier 1; escalate to Tier 2; escalate to Tier 3.

        Confidence threshold: the Phase 3.5 pipeline has its own
        cascade between rule + LLM classifiers; what we check here
        is whether the classifier *converged* (intent != UNCLEAR with
        confidence ≥ TIER1_CONFIDENCE_THRESHOLD)."""
        intent_result = await self.intent_pipeline.classify(query)
        if (
            intent_result.intent != IntentType.UNCLEAR
            and intent_result.confidence >= TIER1_CONFIDENCE_THRESHOLD
        ):
            outcome = await self.intent_dispatcher.dispatch(
                intent_result, user, db
            )
            await self.rate_limiter.record(user.id, tier=TIER_1)
            return RouteResult(
                tier=TIER_1,
                routing_reason=reason,
                text=outcome.text,
                intent=outcome.intent,
                confidence=outcome.confidence,
            )

        # Tier 1 didn't converge — escalate.
        return await self._cascade_tier2_then_3(
            query, user, db, streamer, reason="cascade_from_tier1"
        )

    async def _cascade_tier2_then_3(
        self,
        query: str,
        user: User,
        db: AsyncSession,
        streamer: Streamer | None,
        reason: str,
    ) -> RouteResult:
        """Try Tier 2; if it can't pick a tool, escalate to Tier 3."""
        result = await self.db_agent.answer(query, user, db)
        # Track cost regardless of success — a failed call still
        # billed input tokens.
        await self._record_db_agent_cost(result)

        if result.success:
            text = await format_db_agent_response(result, user, db, query)
            await self.rate_limiter.record(user.id, tier=TIER_2)
            return RouteResult(
                tier=TIER_2,
                routing_reason=reason,
                text=text,
                db_agent_result=result,
            )

        # Tier 2 declined — escalate. Exception: when DeepSeek isn't
        # configured at all we don't escalate (Claude alone won't
        # rescue a config error and the Tier 3 path is more expensive).
        if result.error == "deepseek_not_configured":
            return RouteResult(
                tier=TIER_2,
                routing_reason="tier2_unconfigured",
                text=result.fallback_text or self._unclear_message(),
                db_agent_result=result,
            )

        return await self._handle_tier3(
            query, user, db, streamer,
            reason=f"escalate_from_tier2:{result.error or 'no_tool'}",
        )

    async def _handle_tier3(
        self,
        query: str,
        user: User,
        db: AsyncSession,
        streamer: Streamer | None,
        reason: str,
    ) -> RouteResult:
        """Run Tier 3 with rate-limit gating.

        On rate limit we degrade to Tier 2 (cheap fallback) rather
        than refusing entirely — the user still gets *something*.
        """
        decision = await self.rate_limiter.check_tier3(user.id)
        if not decision.allowed:
            logger.info(
                "tier3 rate limited for user %s, falling back to tier 2",
                user.id,
            )
            # Re-route through Tier 2 only (no further escalation).
            result = await self.db_agent.answer(query, user, db)
            await self._record_db_agent_cost(result)
            text = (
                await format_db_agent_response(result, user, db, query)
                if result.success
                else self._rate_limited_tier3_message(decision.retry_after_seconds)
            )
            await self.rate_limiter.record(user.id, tier=TIER_2)
            return RouteResult(
                tier=TIER_2,
                routing_reason="tier3_rate_limited_degraded_to_tier2",
                text=text,
                db_agent_result=result if result.success else None,
                rate_limited=True,
            )

        if streamer is None:
            # No streamer available — return a graceful note and skip
            # the LLM call. (Caller bug; logging so we notice.)
            logger.warning("Tier 3 routed without streamer; skipping LLM")
            return RouteResult(
                tier=TIER_3,
                routing_reason=reason,
                text="Tính năng phân tích sâu cần phiên Telegram. "
                "Bạn nhắn lại trong Telegram nhé 💚",
            )

        await streamer.start()
        chunks: list[str] = []

        async def on_chunk(chunk: str) -> None:
            chunks.append(chunk)
            await streamer.send_chunk(chunk)

        trace = await self.reasoning_agent.answer_streaming(
            query, user, db, on_chunk
        )
        await streamer.finish()

        # Cost & rate accounting (after the call so we capture real tokens).
        await self.cost_tracker.add(trace.cost_usd)
        await self.rate_limiter.record(user.id, tier=TIER_3)

        return RouteResult(
            tier=TIER_3,
            routing_reason=reason,
            text=None,
            streamed=True,
            reasoning_trace=trace,
        )

    # ------------------------------------------------------------------
    # cost / messages helpers
    # ------------------------------------------------------------------

    async def _record_db_agent_cost(self, result: DBAgentResult) -> None:
        if result.input_tokens is None and result.output_tokens is None:
            return
        from backend.agent.limits import estimate_cost_usd

        cost = estimate_cost_usd(
            model="deepseek-chat",
            input_tokens=result.input_tokens or 0,
            output_tokens=result.output_tokens or 0,
        )
        await self.cost_tracker.add(cost)

    def _unclear_message(self) -> str:
        return (
            "Mình chưa hiểu rõ ý bạn. Có thể hỏi lại cụ thể hơn được không? 🤔"
        )

    def _rate_limited_message(self, retry_after_seconds: int | None) -> str:
        if retry_after_seconds and retry_after_seconds > 60:
            mins = retry_after_seconds // 60
            return (
                f"Bạn đang hỏi nhanh quá! Mình cần nghỉ một lát — "
                f"thử lại sau {mins} phút nhé 🙏"
            )
        return "Bạn đang hỏi nhanh quá! Mình cần nghỉ một lát — thử lại sau nhé 🙏"

    def _rate_limited_tier3_message(self, retry_after_seconds: int | None) -> str:
        return (
            "Mình đã trả lời nhiều câu hỏi sâu hôm nay rồi. "
            "Trong lúc đợi, bạn xem qua dữ liệu nhanh ở trên nhé 💚"
        )

    @staticmethod
    def _load_heuristics(path: Path) -> dict[str, Any]:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise ValueError(f"router_heuristics.yaml must be a mapping at {path}")
        return data


# ---------------------------------------------------------------------------
# Module-level singleton — used by the bot handler. Lazy so import-time
# isn't penalised when the module is just inspected (e.g. by tests).
# ---------------------------------------------------------------------------

_singleton: Orchestrator | None = None


def get_orchestrator() -> Orchestrator:
    global _singleton
    if _singleton is None:
        _singleton = Orchestrator()
    return _singleton


def set_orchestrator(orchestrator: Orchestrator) -> None:
    """Test hook — replace the module-level orchestrator."""
    global _singleton
    _singleton = orchestrator
