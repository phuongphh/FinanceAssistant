"""Tests for the roadmap shortcut (Issue #450 §5).

Covers:
  - Roadmap query pattern matching (lộ trình mua nhà → buy_house).
  - Shared-cache LLM dispatch with timeout fallback.
  - Rule-based fallback content per template id.
  - AdvisoryHandler integration: fast path bypasses rate limit AND
    heavy context build.
"""
from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.intent.handlers.advisory import (
    ADVISORY_EVENT_ROADMAP_SERVED,
    ADVISORY_RATE_LIMIT_PER_DAY,
    AdvisoryHandler,
    DISCLAIMER,
)
from backend.intent.intents import IntentResult, IntentType
from backend.services import goal_roadmap


# ---------------------------------------------------------------------
# Query matching
# ---------------------------------------------------------------------


class TestMatchRoadmapQuery:
    def test_matches_buy_house_with_accents(self):
        assert goal_roadmap.match_roadmap_query(
            "lộ trình mua nhà"
        ) == "buy_house"

    def test_matches_without_accents(self):
        assert goal_roadmap.match_roadmap_query(
            "lo trinh mua nha"
        ) == "buy_house"

    def test_matches_alternative_cue_ke_hoach(self):
        assert goal_roadmap.match_roadmap_query(
            "kế hoạch mua xe"
        ) == "buy_car"

    def test_matches_roadmap_english_cue(self):
        assert goal_roadmap.match_roadmap_query(
            "roadmap mua xe"
        ) == "buy_car"

    def test_returns_none_without_cue_word(self):
        # "mua nhà" alone is a generic query — not a roadmap request.
        assert goal_roadmap.match_roadmap_query("mua nhà") is None

    def test_returns_none_without_template_match(self):
        # Cue is there but no template name → not a recognised roadmap.
        assert goal_roadmap.match_roadmap_query(
            "lộ trình xây dựng sự nghiệp"
        ) is None

    def test_returns_none_for_empty(self):
        assert goal_roadmap.match_roadmap_query("") is None
        assert goal_roadmap.match_roadmap_query(None) is None

    def test_longer_template_name_wins(self):
        # "quỹ khẩn cấp" should beat shorter overlaps. Ensure the
        # longest-match policy is honoured.
        assert goal_roadmap.match_roadmap_query(
            "lộ trình quỹ khẩn cấp"
        ) == "emergency_fund"


# ---------------------------------------------------------------------
# Rule-based fallback
# ---------------------------------------------------------------------


class TestGetFallback:
    def test_buy_house_has_fallback(self):
        fb = goal_roadmap.get_fallback("buy_house")
        assert fb is not None
        assert "mua nhà" in fb.title.lower()
        assert len(fb.steps) >= 4

    def test_all_seven_templates_have_fallback(self):
        """The acceptance criterion says fallback templates exist for
        all 7 goal types from Phase 3.8."""
        from backend.services import goal_templates

        for tpl in goal_templates.list_templates():
            assert goal_roadmap.get_fallback(tpl.id) is not None, (
                f"missing roadmap fallback for {tpl.id}"
            )

    def test_unknown_template_returns_none(self):
        assert goal_roadmap.get_fallback("not_a_template") is None

    def test_render_includes_steps_as_bullets(self):
        fb = goal_roadmap.get_fallback("travel")
        assert fb is not None
        rendered = fb.render()
        for step in fb.steps:
            assert step in rendered
        assert rendered.count("•") == len(fb.steps)


# ---------------------------------------------------------------------
# LLM helper
# ---------------------------------------------------------------------


@pytest.mark.asyncio
class TestCallRoadmapLlm:
    async def test_returns_response_on_success(self):
        db = MagicMock()
        with patch.object(
            goal_roadmap, "call_llm",
            AsyncMock(return_value="bước 1: ...\nbước 2: ..."),
        ) as mock_llm:
            result = await goal_roadmap.call_roadmap_llm(
                db,
                template_id="buy_house",
                goal_name="Mua nhà",
                wealth_level="Trẻ Năng Động",
            )
        assert result == "bước 1: ...\nbước 2: ..."
        mock_llm.assert_awaited_once()
        # Shared cache must be enabled so users at the same tier share.
        kwargs = mock_llm.await_args.kwargs
        assert kwargs["shared_cache"] is True
        # And task_type is distinct from generic advisory so the cache
        # buckets don't collide.
        assert kwargs["task_type"] == "roadmap_advisory"

    async def test_timeout_returns_none(self):
        db = MagicMock()

        async def _slow(*_a, **_kw):
            await asyncio.sleep(10)
            return "never reached"

        # Override the timeout to a tiny value so the test is fast.
        with patch.object(goal_roadmap, "LLM_TIMEOUT_SECONDS", 0.05), \
             patch.object(goal_roadmap, "call_llm", _slow):
            result = await goal_roadmap.call_roadmap_llm(
                db,
                template_id="buy_house",
                goal_name="Mua nhà",
                wealth_level="Trẻ Năng Động",
            )
        assert result is None

    async def test_llm_error_returns_none(self):
        from backend.services.llm_service import LLMError

        db = MagicMock()
        with patch.object(
            goal_roadmap, "call_llm",
            AsyncMock(side_effect=LLMError("boom")),
        ):
            result = await goal_roadmap.call_roadmap_llm(
                db,
                template_id="buy_house",
                goal_name="Mua nhà",
                wealth_level="Trẻ Năng Động",
            )
        assert result is None


# ---------------------------------------------------------------------
# AdvisoryHandler integration
# ---------------------------------------------------------------------


def _user(level: str = "young_prof"):
    user = MagicMock()
    user.id = uuid.uuid4()
    user.display_name = "Test"
    user.monthly_income = None
    user.wealth_level = level
    return user


def _db():
    db = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    return db


@pytest.mark.asyncio
class TestAdvisoryRoadmapIntegration:
    async def test_roadmap_query_bypasses_rate_limit(self):
        """Roadmap responses must NOT consume the daily advisory quota
        — they're cacheable and not personalised enough to count."""
        user = _user()
        intent = IntentResult(
            intent=IntentType.ADVISORY,
            confidence=0.95,
            raw_text="lộ trình mua nhà",
        )
        with patch(
            "backend.intent.handlers.advisory._advisory_calls_in_last_24h",
            AsyncMock(return_value=ADVISORY_RATE_LIMIT_PER_DAY + 10),
        ) as rate_check, patch.object(
            goal_roadmap, "call_roadmap_llm",
            AsyncMock(return_value="bước 1: tích lũy 30% giá trị."),
        ):
            response = await AdvisoryHandler().handle(intent, user, _db())

        rate_check.assert_not_called()
        assert "bước 1" in response
        assert DISCLAIMER in response

    async def test_roadmap_uses_fallback_when_llm_times_out(self):
        user = _user()
        intent = IntentResult(
            intent=IntentType.ADVISORY,
            confidence=0.95,
            raw_text="lộ trình mua nhà",
        )
        with patch.object(
            goal_roadmap, "call_roadmap_llm", AsyncMock(return_value=None),
        ):
            response = await AdvisoryHandler().handle(intent, user, _db())

        # Fallback template renders the buy_house title and the
        # disclaimer-plus-retry note from the handler.
        assert "mua nhà" in response.lower()
        assert "thử lại sau" in response
        assert DISCLAIMER in response

    async def test_roadmap_does_not_build_heavy_context(self):
        """Performance assertion: when the fast path matches we MUST
        skip the expensive ``_build_context`` because that's why the
        old "lộ trình mua nhà" was slow."""
        user = _user()
        intent = IntentResult(
            intent=IntentType.ADVISORY,
            confidence=0.95,
            raw_text="lộ trình mua nhà",
        )
        with patch(
            "backend.intent.handlers.advisory._build_context",
            AsyncMock(return_value={}),
        ) as build, patch.object(
            goal_roadmap, "call_roadmap_llm",
            AsyncMock(return_value="..."),
        ):
            await AdvisoryHandler().handle(intent, user, _db())

        build.assert_not_called()

    async def test_non_roadmap_query_falls_through_to_normal_advisory(self):
        """A non-roadmap advisory query must keep the old behaviour:
        build context, hit rate limiter, call LLM with user context."""
        user = _user()
        intent = IntentResult(
            intent=IntentType.ADVISORY,
            confidence=0.9,
            raw_text="có nên đầu tư crypto không",
        )
        with patch(
            "backend.intent.handlers.advisory._advisory_calls_in_last_24h",
            AsyncMock(return_value=0),
        ), patch(
            "backend.intent.handlers.advisory._build_context",
            AsyncMock(return_value={
                "name": "Test", "level": "Trẻ Năng Động",
                "net_worth": "100tr", "breakdown": "x", "income": "y",
                "goals": "z", "recent_spend": "w",
                "conversation_history": "",
            }),
        ) as build, patch(
            "backend.intent.handlers.advisory.call_llm",
            AsyncMock(return_value="Hãy cân nhắc..."),
        ):
            response = await AdvisoryHandler().handle(intent, user, _db())

        build.assert_awaited_once()
        assert "Hãy cân nhắc" in response

    async def test_roadmap_emits_served_event(self):
        from backend import analytics

        captured: list[tuple] = []

        def _capture(event_type, user_id=None, properties=None):
            captured.append((event_type, properties))

        user = _user()
        intent = IntentResult(
            intent=IntentType.ADVISORY,
            confidence=0.95,
            raw_text="lộ trình mua nhà",
        )
        original = analytics.track
        analytics.track = _capture
        try:
            with patch.object(
                goal_roadmap, "call_roadmap_llm",
                AsyncMock(return_value="bước 1..."),
            ):
                await AdvisoryHandler().handle(intent, user, _db())
        finally:
            analytics.track = original

        events = [(name, props) for name, props in captured]
        roadmap_events = [
            (name, props) for name, props in events
            if name == ADVISORY_EVENT_ROADMAP_SERVED
        ]
        assert len(roadmap_events) == 1
        assert roadmap_events[0][1]["template_id"] == "buy_house"
        assert roadmap_events[0][1]["source"] == "llm"
