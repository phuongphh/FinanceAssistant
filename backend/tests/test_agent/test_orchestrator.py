"""Orchestrator routing tests — heuristics + cascade + rate-limit gating.

Heuristic tests are pure (no async) — they verify regex matching
against the YAML fixtures. The cascade + tier integration tests stub
each downstream agent so we exercise routing decisions without LLMs.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.agent.orchestrator import (
    AMBIGUOUS,
    Orchestrator,
    TIER_1,
    TIER_2,
    TIER_3,
    RouteResult,
)
from backend.agent.rate_limit import DailyCostTracker, RateLimiter
from backend.agent.tier2.db_agent import DBAgentResult
from backend.agent.tier3.reasoning_agent import ReasoningTrace
from backend.intent.intents import IntentResult, IntentType


# ---------------------------------------------------------------------------
# Heuristic classification fixtures (the spec asks for ≥85% accuracy).
# ---------------------------------------------------------------------------

ROUTING_FIXTURES = [
    # ---- Tier 2 ----
    ("Mã chứng khoán nào của tôi đang lãi?", TIER_2),
    ("Liệt kê các mã đang lỗ", TIER_2),
    ("Top 3 mã lãi nhiều nhất", TIER_2),
    ("Top 5 chi tiêu lớn nhất tháng này", TIER_2),
    ("Tài sản trên 1 tỷ", TIER_2),
    ("Tài sản dưới 100 triệu", TIER_2),
    ("Tổng lãi portfolio của tôi", TIER_2),
    ("Trung bình chi tiêu 6 tháng qua", TIER_2),
    ("Tỷ lệ tiết kiệm tháng này", TIER_2),
    ("Chi tháng này so với tháng trước", TIER_2),
    ("VNM vs HPG", TIER_2),
    ("Mã có giá trị cao nhất", TIER_2),
    ("Cổ phiếu lớn nhất", TIER_2),
    ("Cao nhất là mã nào", TIER_2),
    ("Chênh lệch chi tiêu", TIER_2),
    # ---- Tier 3 ----
    ("Có nên bán FLC để cắt lỗ không?", TIER_3),
    ("Làm thế nào để đạt mục tiêu mua xe trong 2 năm?", TIER_3),
    ("Nếu tôi giảm chi 20% thì tiết kiệm được bao nhiêu?", TIER_3),
    ("Tư vấn giúp mình portfolio", TIER_3),
    ("Tại sao chi tiêu tháng này tăng?", TIER_3),
    # ---- Ambiguous (cascade through Tier 1 first) ----
    ("Tài sản của tôi có gì?", AMBIGUOUS),
    ("VNM giá bao nhiêu?", AMBIGUOUS),
    ("Hello", AMBIGUOUS),
    ("Tôi nắm 100 cổ VNM", AMBIGUOUS),
    ("Chi tiêu hôm nay", AMBIGUOUS),
    ("Mục tiêu của tôi", AMBIGUOUS),
    ("Đặt mục tiêu 100tr", AMBIGUOUS),
    ("Báo cáo tháng này", AMBIGUOUS),
    ("Help", AMBIGUOUS),
]


class TestHeuristics:
    @pytest.mark.parametrize("query,expected", ROUTING_FIXTURES)
    def test_routing_accuracy(self, query, expected):
        orch = _orch_skeleton()
        actual = orch._heuristic_classify(query)
        assert actual == expected, f"{query!r}: got {actual}, expected {expected}"

    def test_overall_accuracy_above_85(self):
        orch = _orch_skeleton()
        right = sum(
            1 for q, exp in ROUTING_FIXTURES
            if orch._heuristic_classify(q) == exp
        )
        accuracy = right / len(ROUTING_FIXTURES)
        # The spec asks for ≥85% — leave headroom in case fixtures expand.
        assert accuracy >= 0.85, f"routing accuracy {accuracy:.0%} below 85%"


# ---------------------------------------------------------------------------
# Cascade behaviour — full path with stubbed agents.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCascade:
    async def test_clear_tier3_signal_skips_tier1_2(self):
        orch = _orch_with_streamable()
        result = await orch.route(
            "có nên bán FLC không?", _user(), MagicMock(), streamer=_streamer()
        )
        assert result.tier == TIER_3
        assert result.routing_reason == "heuristic_tier3"

    async def test_clear_tier2_signal_uses_db_agent(self):
        orch = _orch_with_streamable()
        # DBAgent stubbed to succeed.
        orch.db_agent.answer = AsyncMock(  # type: ignore[assignment]
            return_value=_ok_db_result()
        )
        # Format function stubbed via monkey-patching the orchestrator method.
        async def fake_format(_a, _b, _c, _d): return "asset list text"
        import backend.agent.orchestrator as orch_mod
        orig = orch_mod.format_db_agent_response
        orch_mod.format_db_agent_response = fake_format  # type: ignore[assignment]
        try:
            result = await orch.route(
                "top 3 mã lãi nhất", _user(), MagicMock(), streamer=None
            )
        finally:
            orch_mod.format_db_agent_response = orig  # type: ignore[assignment]
        assert result.tier == TIER_2
        assert result.text == "asset list text"

    async def test_ambiguous_uses_tier1_when_high_confidence(self):
        orch = _orch_with_streamable()
        # Tier 1 confident.
        orch.intent_pipeline.classify = AsyncMock(  # type: ignore[assignment]
            return_value=IntentResult(
                intent=IntentType.QUERY_ASSETS,
                confidence=0.95,
                raw_text="tài sản của tôi",
            )
        )
        orch.intent_dispatcher.dispatch = AsyncMock(  # type: ignore[assignment]
            return_value=MagicMock(
                text="tài sản: VNM, HPG",
                intent=IntentType.QUERY_ASSETS,
                confidence=0.95,
            )
        )
        result = await orch.route(
            "tài sản của tôi", _user(), MagicMock(), streamer=None
        )
        assert result.tier == TIER_1
        assert result.text == "tài sản: VNM, HPG"

    async def test_ambiguous_escalates_when_tier1_uncertain(self):
        orch = _orch_with_streamable()
        # Tier 1 uncertain → escalate to Tier 2.
        orch.intent_pipeline.classify = AsyncMock(  # type: ignore[assignment]
            return_value=IntentResult(
                intent=IntentType.UNCLEAR,
                confidence=0.0,
                raw_text="?",
            )
        )
        orch.db_agent.answer = AsyncMock(  # type: ignore[assignment]
            return_value=_ok_db_result()
        )
        async def fake_format(_a, _b, _c, _d): return "tier2 text"
        import backend.agent.orchestrator as orch_mod
        orig = orch_mod.format_db_agent_response
        orch_mod.format_db_agent_response = fake_format  # type: ignore[assignment]
        try:
            result = await orch.route(
                "??", _user(), MagicMock(), streamer=None
            )
        finally:
            orch_mod.format_db_agent_response = orig  # type: ignore[assignment]
        assert result.tier == TIER_2
        assert "cascade" in result.routing_reason

    async def test_tier2_failure_escalates_to_tier3(self):
        orch = _orch_with_streamable()
        orch.intent_pipeline.classify = AsyncMock(  # type: ignore[assignment]
            return_value=IntentResult(
                intent=IntentType.UNCLEAR,
                confidence=0.0,
                raw_text="?",
            )
        )
        orch.db_agent.answer = AsyncMock(  # type: ignore[assignment]
            return_value=DBAgentResult(success=False, error="no_tool_selected")
        )
        # Streamer required for Tier 3 path.
        result = await orch.route(
            "phân tích portfolio", _user(), MagicMock(), streamer=_streamer()
        )
        assert result.tier == TIER_3
        assert "escalate_from_tier2" in result.routing_reason

    async def test_tier2_unconfigured_does_not_escalate(self):
        orch = _orch_with_streamable()
        orch.intent_pipeline.classify = AsyncMock(  # type: ignore[assignment]
            return_value=IntentResult(
                intent=IntentType.UNCLEAR,
                confidence=0.0,
                raw_text="?",
            )
        )
        orch.db_agent.answer = AsyncMock(  # type: ignore[assignment]
            return_value=DBAgentResult(
                success=False, error="deepseek_not_configured",
                fallback_text="key chưa cấu hình"
            )
        )
        result = await orch.route(
            "?", _user(), MagicMock(), streamer=_streamer()
        )
        # Stays at Tier 2 with the configured fallback text.
        assert result.tier == TIER_2
        assert result.routing_reason == "tier2_unconfigured"


# ---------------------------------------------------------------------------
# Rate limit + cost gates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGates:
    async def test_total_rate_limit_short_circuits(self):
        rl = RateLimiter(max_total_per_hour=0)  # always over
        orch = _orch_with_streamable(rate_limiter=rl)
        result = await orch.route(
            "anything", _user(), MagicMock(), streamer=None
        )
        assert result.rate_limited is True
        assert "nghỉ một lát" in (result.text or "")

    async def test_tier3_rate_limit_degrades_to_tier2(self):
        rl = RateLimiter(max_total_per_hour=100, max_tier3_per_hour=0)
        orch = _orch_with_streamable(rate_limiter=rl)
        orch.db_agent.answer = AsyncMock(  # type: ignore[assignment]
            return_value=_ok_db_result()
        )
        async def fake_format(_a, _b, _c, _d): return "fallback tier2 answer"
        import backend.agent.orchestrator as orch_mod
        orig = orch_mod.format_db_agent_response
        orch_mod.format_db_agent_response = fake_format  # type: ignore[assignment]
        try:
            result = await orch.route(
                "có nên bán FLC?", _user(), MagicMock(), streamer=_streamer()
            )
        finally:
            orch_mod.format_db_agent_response = orig  # type: ignore[assignment]
        assert result.tier == TIER_2
        assert result.rate_limited is True

    async def test_cost_kill_switch(self):
        # Hard limit at 0 → never spend.
        ct = DailyCostTracker(alert_threshold_usd=0.0, hard_limit_usd=0.001)
        # Pre-load the bucket past the limit.
        await ct.add(0.01)
        orch = _orch_with_streamable(cost_tracker=ct)
        result = await orch.route(
            "anything", _user(), MagicMock(), streamer=None
        )
        assert result.tier == "kill_switch"
        assert "cân đối chi phí" in (result.text or "")


@pytest.mark.asyncio
class TestTier3StreamingPath:
    async def test_tier3_invokes_streamer_lifecycle(self):
        orch = _orch_with_streamable()
        # Stub the reasoning agent to emit one chunk + return success.
        async def fake_answer(query, user, db, on_chunk):
            await on_chunk("Đây là phân tích.")
            return ReasoningTrace(
                success=True, final_text="Đây là phân tích.",
                cost_usd=0.001, latency_ms=100, input_tokens=100,
                output_tokens=20,
            )

        orch.reasoning_agent.answer_streaming = fake_answer  # type: ignore[assignment]

        streamer = _streamer()
        result = await orch.route(
            "có nên bán FLC?", _user(), MagicMock(), streamer=streamer
        )
        assert result.tier == TIER_3
        assert result.streamed is True
        assert result.text is None
        streamer.start.assert_awaited_once()
        streamer.send_chunk.assert_awaited()
        streamer.finish.assert_awaited_once()

    async def test_tier3_without_streamer_returns_graceful(self):
        orch = _orch_with_streamable()
        result = await orch.route(
            "có nên bán FLC?", _user(), MagicMock(), streamer=None
        )
        assert result.tier == TIER_3
        assert result.streamed is False
        assert result.text and "Telegram" in result.text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _user():
    u = MagicMock()
    u.id = uuid.uuid4()
    u.display_name = "Hà"
    return u


def _streamer():
    s = MagicMock()
    s.start = AsyncMock()
    s.send_chunk = AsyncMock()
    s.finish = AsyncMock()
    return s


def _ok_db_result():
    return DBAgentResult(
        success=True,
        tool_called="get_assets",
        tool_args={"limit": 3},
        result={"assets": [], "total_value": "0", "count": 0},
        input_tokens=100,
        output_tokens=20,
    )


def _orch_skeleton() -> Orchestrator:
    """Build an orchestrator with no-op agents for heuristic tests."""
    return Orchestrator(
        intent_pipeline=MagicMock(),
        intent_dispatcher=MagicMock(),
        db_agent=MagicMock(),
        reasoning_agent=MagicMock(),
        rate_limiter=RateLimiter(),
        cost_tracker=DailyCostTracker(),
    )


def _orch_with_streamable(
    *,
    rate_limiter: RateLimiter | None = None,
    cost_tracker: DailyCostTracker | None = None,
) -> Orchestrator:
    """Orchestrator with mocked LLM agents but real cascade flow.

    Both downstream agents have async-aware default stubs so a test
    that doesn't override them gets sensible non-failing behaviour
    (intent pipeline → UNCLEAR; db_agent → no-tool fallback;
    reasoning agent → empty trace). Tests that exercise specific
    paths replace the relevant method explicitly."""
    intent_pipeline = MagicMock()
    intent_pipeline.classify = AsyncMock(
        return_value=IntentResult(
            intent=IntentType.UNCLEAR, confidence=0.0, raw_text=""
        )
    )
    intent_dispatcher = MagicMock()
    intent_dispatcher.dispatch = AsyncMock()

    db_agent = MagicMock()
    db_agent.answer = AsyncMock(
        return_value=DBAgentResult(success=False, error="no_tool_selected")
    )

    reasoning_agent = MagicMock()
    reasoning_agent.answer_streaming = AsyncMock(
        return_value=ReasoningTrace(success=True, final_text="ok", cost_usd=0.0)
    )

    return Orchestrator(
        intent_pipeline=intent_pipeline,
        intent_dispatcher=intent_dispatcher,
        db_agent=db_agent,
        reasoning_agent=reasoning_agent,
        rate_limiter=rate_limiter or RateLimiter(),
        cost_tracker=cost_tracker or DailyCostTracker(),
    )
