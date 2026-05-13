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
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent import caching
from backend.agent.audit import RouteAudit, log_route
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
from backend.models.conversation_context import ROLE_ASSISTANT, ROLE_USER
from backend.models.user import User
from backend.services import conversation_context_service

logger = logging.getLogger(__name__)

TIER_1 = "tier1"
TIER_2 = "tier2"
TIER_3 = "tier3"
AMBIGUOUS = "ambiguous"

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
    # When the orchestrator delegated to Phase 3.5 (Tier 1) we keep
    # the full DispatchOutcome so callers can render the inline
    # keyboard / track the right kind without reaching back into
    # the dispatcher themselves.
    dispatch_outcome: DispatchOutcome | None = None


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
        cache_enabled: bool = True,
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
        self.cache_enabled = cache_enabled

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
        audit: bool = True,
    ) -> RouteResult:
        """Route ``query``, return the result, fire-and-forget audit log.

        ``streamer`` is required for Tier 3 — a Tier 3 query without
        a streamer would silently lose its reasoning output. We
        still allow it (returning ``text=None``) so callers like
        unit tests can use a fake streamer if they want one.

        ``audit=False`` skips the audit-log write — used by tests
        that don't want the background task lingering after the test
        scope ends. Production calls should always leave this on.
        """
        started = time.monotonic()
        # Load prior conversation turns BEFORE routing so the LLM call
        # in Tier 2/3 can see the history. Saving the current turn
        # (user message + assistant reply) happens AFTER routing so
        # this turn doesn't appear in its own history.
        history = await conversation_context_service.get_recent_messages(
            db, user_id=user.id
        )
        result = await self._route_inner(
            query, user, db, streamer=streamer, history=history
        )
        await self._record_conversation_turn(
            db, user=user, query=query, result=result
        )
        if audit:
            try:
                log_route(
                    self._build_audit(
                        query=query,
                        user=user,
                        result=result,
                        latency_ms=int((time.monotonic() - started) * 1000),
                    )
                )
            except Exception:
                # Audit must never tank a real response.
                logger.debug("audit log emit failed", exc_info=True)
        return result

    async def _route_inner(
        self,
        query: str,
        user: User,
        db: AsyncSession,
        *,
        streamer: Streamer | None,
        history: list | None = None,
    ) -> RouteResult:
        """Core routing logic — extracted so ``route`` can wrap it
        in an audit boundary without nesting indentation."""
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
                query, user, db, streamer,
                reason="heuristic_tier3", history=history,
            )
        if tier_hint == TIER_2:
            return await self._cascade_tier2_then_3(
                query, user, db, streamer,
                reason="heuristic_tier2", history=history,
            )

        # Ambiguous — try Tier 1 first.
        return await self._cascade_tier1_then_up(
            query, user, db, streamer,
            reason="cascade", history=history,
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
        history: list | None = None,
    ) -> RouteResult:
        """Try Tier 1; escalate to Tier 2 only when Tier 1 truly
        can't classify.

        We hand any non-UNCLEAR intent straight to the dispatcher —
        even at low confidence — because the dispatcher already
        handles the clarify/confirm flow for medium-confidence cases.
        Bypassing it for "low confidence" would skip those flows and
        send confusing answers to Tier 2."""
        intent_result = await self.intent_pipeline.classify(query)
        if intent_result.intent != IntentType.UNCLEAR:
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
                dispatch_outcome=outcome,
            )

        # Tier 1 didn't converge — escalate.
        return await self._cascade_tier2_then_3(
            query, user, db, streamer,
            reason="cascade_from_tier1", history=history,
        )

    async def _cascade_tier2_then_3(
        self,
        query: str,
        user: User,
        db: AsyncSession,
        streamer: Streamer | None,
        reason: str,
        history: list | None = None,
    ) -> RouteResult:
        """Try Tier 2; if it can't pick a tool, escalate to Tier 3.

        Cache lookup happens BEFORE the LLM call — a hit replays the
        same DBAgentResult without spending tokens. Misses execute
        the agent and write the result back."""
        cached = await self._cache_get_tier2(db, user.id, query)
        if cached is not None:
            text = await format_db_agent_response(cached, user, db, query)
            await self.rate_limiter.record(user.id, tier=TIER_2)
            return RouteResult(
                tier=TIER_2,
                routing_reason=f"{reason}+cache_hit",
                text=text,
                db_agent_result=cached,
            )

        result = await self.db_agent.answer(query, user, db, history=history)
        # Track cost regardless of success — a failed call still
        # billed input tokens.
        await self._record_db_agent_cost(result)

        if result.success:
            await self._cache_set_tier2(db, user.id, query, result)
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
            history=history,
        )

    async def _handle_tier3(
        self,
        query: str,
        user: User,
        db: AsyncSession,
        streamer: Streamer | None,
        reason: str,
        history: list | None = None,
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
            result = await self.db_agent.answer(query, user, db, history=history)
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

        # Cache lookup — replay a recent answer without burning Sonnet
        # tokens. We still send through the streamer so the user gets
        # the same UX (typing indicator + message) as a fresh call.
        cached_text = await self._cache_get_tier3(db, user.id, query)
        if cached_text is not None:
            await streamer.start()
            await streamer.send_chunk(cached_text)
            await streamer.finish()
            await self.rate_limiter.record(user.id, tier=TIER_3)
            return RouteResult(
                tier=TIER_3,
                routing_reason=f"{reason}+cache_hit",
                text=None,
                streamed=True,
            )

        await streamer.start()
        chunks: list[str] = []

        async def on_chunk(chunk: str) -> None:
            chunks.append(chunk)
            await streamer.send_chunk(chunk)

        trace = await self.reasoning_agent.answer_streaming(
            query, user, db, on_chunk, history=history
        )
        await streamer.finish()

        # Cost & rate accounting (after the call so we capture real tokens).
        await self.cost_tracker.add(trace.cost_usd)
        await self.rate_limiter.record(user.id, tier=TIER_3)

        # Cache the assembled response only when the call succeeded —
        # caching error messages would just lock the user out for an hour.
        if trace.success and trace.final_text:
            await self._cache_set_tier3(db, user.id, query, trace.final_text)

        return RouteResult(
            tier=TIER_3,
            routing_reason=reason,
            text=None,
            streamed=True,
            reasoning_trace=trace,
        )

    # ------------------------------------------------------------------
    # conversation context (short-term buffer)
    # ------------------------------------------------------------------

    async def _record_conversation_turn(
        self,
        db: AsyncSession,
        *,
        user: User,
        query: str,
        result: RouteResult,
    ) -> None:
        """Append the user/assistant pair to the rolling buffer.

        Skips rate-limit / kill-switch outcomes — those aren't real
        turns and the user will retry, so storing them just clutters
        the next prompt's window. Truncation happens inside the service.
        """
        if result.tier in ("rate_limited", "kill_switch"):
            return
        intent_value = (
            result.intent.value if result.intent is not None else None
        )
        await conversation_context_service.save_message(
            db, user_id=user.id, role=ROLE_USER,
            content=query, intent=intent_value,
        )
        assistant_text = result.text
        if not assistant_text and result.reasoning_trace is not None:
            # Tier 3 streamed its answer — pull the full text from the
            # trace so the buffer has something useful for next-turn
            # prompts. Fine if final_text is empty (e.g. timeout); the
            # service skips empty content.
            assistant_text = result.reasoning_trace.final_text
        if assistant_text:
            await conversation_context_service.save_message(
                db, user_id=user.id, role=ROLE_ASSISTANT,
                content=assistant_text, intent=intent_value,
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

    # ----- cache helpers (failures are non-fatal) ---------------------

    async def _cache_get_tier2(
        self, db: AsyncSession, user_id, query: str
    ) -> DBAgentResult | None:
        if not self.cache_enabled:
            return None
        try:
            raw = await caching.get_tier2(db, user_id=user_id, query=query)
        except Exception:
            logger.debug("tier2 cache lookup failed", exc_info=True)
            return None
        if raw is None:
            return None
        # The stored shape is the dataclass dict — reconstruct so the
        # downstream formatter sees the same type a fresh call would.
        return DBAgentResult(
            success=raw.get("success", False),
            tool_called=raw.get("tool_called"),
            tool_args=raw.get("tool_args"),
            result=raw.get("result"),
            error=raw.get("error"),
            fallback_text=raw.get("fallback_text"),
            latency_ms=raw.get("latency_ms", 0),
            input_tokens=raw.get("input_tokens"),
            output_tokens=raw.get("output_tokens"),
        )

    async def _cache_set_tier2(
        self, db: AsyncSession, user_id, query: str, result: DBAgentResult
    ) -> None:
        if not self.cache_enabled:
            return
        try:
            await caching.set_tier2(
                db, user_id=user_id, query=query, result=result.to_dict()
            )
        except Exception:
            logger.debug("tier2 cache set failed", exc_info=True)

    async def _cache_get_tier3(
        self, db: AsyncSession, user_id, query: str
    ) -> str | None:
        if not self.cache_enabled:
            return None
        try:
            return await caching.get_tier3(db, user_id=user_id, query=query)
        except Exception:
            logger.debug("tier3 cache lookup failed", exc_info=True)
            return None

    async def _cache_set_tier3(
        self, db: AsyncSession, user_id, query: str, response: str
    ) -> None:
        if not self.cache_enabled:
            return
        try:
            await caching.set_tier3(
                db, user_id=user_id, query=query, response=response
            )
        except Exception:
            logger.debug("tier3 cache set failed", exc_info=True)

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

    def _build_audit(
        self,
        *,
        query: str,
        user: User,
        result: RouteResult,
        latency_ms: int,
    ) -> RouteAudit:
        """Pack a RouteResult into the dataclass the audit writer wants.

        Pulls model / token / cost fields out of whichever sub-result
        is populated (tier 2 → DBAgentResult, tier 3 → ReasoningTrace,
        tier 1 → none of either since intent layer accounts separately
        via analytics events)."""
        tools_called: list[dict[str, Any]] = []
        tool_call_count = 0
        llm_model: str | None = None
        input_tokens: int | None = None
        output_tokens: int | None = None
        cost_usd: float | None = None
        success = bool(result.text or result.streamed)
        error: str | None = None

        if result.db_agent_result is not None:
            r = result.db_agent_result
            tool_call_count = 1 if r.tool_called else 0
            if r.tool_called:
                tools_called = [
                    {"name": r.tool_called, "args": r.tool_args or {}}
                ]
            llm_model = "deepseek-chat"
            input_tokens = r.input_tokens
            output_tokens = r.output_tokens
            from backend.agent.limits import estimate_cost_usd

            cost_usd = estimate_cost_usd(
                model=llm_model,
                input_tokens=r.input_tokens or 0,
                output_tokens=r.output_tokens or 0,
            )
            success = r.success
            error = r.error

        if result.reasoning_trace is not None:
            t = result.reasoning_trace
            tools_called = list(t.tool_calls)
            tool_call_count = t.tool_call_count
            llm_model = "claude-sonnet"
            input_tokens = t.input_tokens
            output_tokens = t.output_tokens
            cost_usd = t.cost_usd
            success = t.success
            error = t.error

        response_preview = result.text or (
            result.reasoning_trace.final_text
            if result.reasoning_trace
            else None
        )

        return RouteAudit(
            user_id=getattr(user, "id", None),
            query_text=query,
            tier_used=result.tier,
            routing_reason=result.routing_reason,
            tools_called=tools_called,
            tool_call_count=tool_call_count,
            llm_model=llm_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            success=success,
            response_preview=response_preview,
            error=error,
            total_latency_ms=latency_ms,
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
