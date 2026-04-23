"""Unit tests for memory_moments — weekly goal reminder (Issue #44).

Each of the 4 goal codes produces distinct, contextually-correct text:
- save_more      → includes last week's spend
- understand     → includes top category name + amount
- reach_goal     → includes goal name + remaining
- less_stress    → includes positive signal (comparative or categorical)

Skip conditions:
- No primary_goal → returns None
- Inactive last 7 days → returns None
- reach_goal with no active Goal row → returns None
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.bot.personality import memory_moments
from backend.models.user import User


def _make_user(goal: str | None = None, name: str = "Minh") -> User:
    u = User()
    u.id = uuid.uuid4()
    u.telegram_id = 333
    u.display_name = name
    u.primary_goal = goal
    u.onboarding_skipped = False
    u.onboarding_completed_at = datetime.now(timezone.utc)
    return u


def _scalar(value):
    r = MagicMock()
    r.scalar_one.return_value = value
    r.scalar_one_or_none.return_value = value
    return r


@pytest.mark.asyncio
class TestSkipConditions:
    async def test_no_primary_goal_returns_none(self):
        user = _make_user(goal=None)
        db = MagicMock()
        out = await memory_moments.render_goal_reminder(
            db, user, today=date(2026, 4, 27),
        )
        assert out is None

    async def test_inactive_last_week_returns_none(self):
        user = _make_user(goal="save_more")
        db = MagicMock()
        # was_active_last_week → count = 0
        db.execute = AsyncMock(return_value=_scalar(0))
        out = await memory_moments.render_goal_reminder(
            db, user, today=date(2026, 4, 27),
        )
        assert out is None

    async def test_unknown_goal_code_returns_none(self):
        user = _make_user(goal="weird_unknown_code")
        db = MagicMock()
        out = await memory_moments.render_goal_reminder(
            db, user, today=date(2026, 4, 27),
        )
        assert out is None


@pytest.mark.asyncio
class TestSaveMoreContext:
    async def test_includes_last_week_amount(self):
        user = _make_user(goal="save_more", name="Hoa")

        # Patch was_active_last_week to True, and supply context numbers.
        with patch(
            "backend.bot.personality.memory_moments.was_active_last_week",
            new_callable=AsyncMock, return_value=True,
        ), patch(
            "backend.bot.personality.memory_moments._context_save_more",
            new_callable=AsyncMock,
            return_value={
                "last_week_spent": "1,200,000đ",
                "encouragement": "đều đặn lắm 🙂",
            },
        ):
            out = await memory_moments.render_goal_reminder(
                MagicMock(), user, today=date(2026, 4, 27),
            )
        assert out is not None
        assert "1,200,000đ" in out
        assert "Hoa" in out


@pytest.mark.asyncio
class TestUnderstandContext:
    async def test_includes_top_category_label(self):
        user = _make_user(goal="understand", name="Tuan")

        with patch(
            "backend.bot.personality.memory_moments.was_active_last_week",
            new_callable=AsyncMock, return_value=True,
        ), patch(
            "backend.bot.personality.memory_moments._context_understand",
            new_callable=AsyncMock,
            return_value={
                "top_cat": "Ăn uống",
                "top_amount": "850,000đ",
                "top_pct": "42",
            },
        ):
            out = await memory_moments.render_goal_reminder(
                MagicMock(), user, today=date(2026, 4, 27),
            )
        assert out is not None
        assert "Ăn uống" in out
        assert "850,000đ" in out

    async def test_no_top_category_returns_none(self):
        user = _make_user(goal="understand")
        with patch(
            "backend.bot.personality.memory_moments.was_active_last_week",
            new_callable=AsyncMock, return_value=True,
        ), patch(
            "backend.bot.personality.memory_moments._context_understand",
            new_callable=AsyncMock, return_value=None,
        ):
            out = await memory_moments.render_goal_reminder(
                MagicMock(), user, today=date(2026, 4, 27),
            )
        assert out is None


@pytest.mark.asyncio
class TestReachGoalContext:
    async def test_includes_goal_name_and_remaining(self):
        user = _make_user(goal="reach_goal", name="Lan")
        with patch(
            "backend.bot.personality.memory_moments.was_active_last_week",
            new_callable=AsyncMock, return_value=True,
        ), patch(
            "backend.bot.personality.memory_moments._context_reach_goal",
            new_callable=AsyncMock,
            return_value={
                "goal_name": "Mua macbook",
                "remaining": "18,000,000đ",
                "progress_pct": "40",
            },
        ):
            out = await memory_moments.render_goal_reminder(
                MagicMock(), user, today=date(2026, 4, 27),
            )
        assert out is not None
        assert "Mua macbook" in out
        assert "18,000,000đ" in out

    async def test_no_active_goal_returns_none(self):
        user = _make_user(goal="reach_goal")
        with patch(
            "backend.bot.personality.memory_moments.was_active_last_week",
            new_callable=AsyncMock, return_value=True,
        ), patch(
            "backend.bot.personality.memory_moments._context_reach_goal",
            new_callable=AsyncMock, return_value=None,
        ):
            out = await memory_moments.render_goal_reminder(
                MagicMock(), user, today=date(2026, 4, 27),
            )
        assert out is None


@pytest.mark.asyncio
class TestLessStressContext:
    async def test_always_returns_positive_signal(self):
        user = _make_user(goal="less_stress", name="Phu")
        with patch(
            "backend.bot.personality.memory_moments.was_active_last_week",
            new_callable=AsyncMock, return_value=True,
        ), patch(
            "backend.bot.personality.memory_moments._context_less_stress",
            new_callable=AsyncMock,
            return_value={"positive_signal": "tuần vừa rồi khá ổn định."},
        ):
            out = await memory_moments.render_goal_reminder(
                MagicMock(), user, today=date(2026, 4, 27),
            )
        assert out is not None
        assert "Phu" in out
        assert "tuần" in out.lower()


class TestTemplateCoverage:
    def test_all_four_goals_have_templates(self):
        required = {"save_more", "understand", "reach_goal", "less_stress"}
        for g in required:
            assert g in memory_moments.GOAL_REMINDER_TEMPLATES
            assert len(memory_moments.GOAL_REMINDER_TEMPLATES[g]) >= 1
