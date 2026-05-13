"""Tests for the daily milestone check-and-celebrate job.

Focus on the review-flagged edge cases:
- per-user cap now preserves skipped rows for the next run
- failed Telegram sends do not stamp celebrated_at
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.jobs import check_milestones
from backend.models.user import User
from backend.models.user_milestone import MilestoneType, UserMilestone


def _make_user() -> User:
    u = User()
    u.id = uuid.uuid4()
    u.telegram_id = 999
    u.display_name = "Minh"
    u.onboarding_skipped = False
    u.onboarding_completed_at = None
    u.is_active = True
    return u


def _make_pending(m_type: str) -> UserMilestone:
    m = UserMilestone()
    m.id = uuid.uuid4()
    m.user_id = uuid.uuid4()
    m.milestone_type = m_type
    m.achieved_at = datetime.now(timezone.utc)
    m.celebrated_at = None
    m.extra = {"count": 1}
    return m


@pytest.mark.asyncio
async def test_cap_leaves_extra_milestones_for_next_run():
    """When pending > cap, only the cap count is marked celebrated."""
    user = _make_user()
    pending = [
        _make_pending(MilestoneType.DAYS_7),
        _make_pending(MilestoneType.STREAK_7),
        _make_pending(MilestoneType.FIRST_TRANSACTION),
    ]

    mark_celebrated_mock = AsyncMock()

    class _FakeSession:
        # Job now owns the commit boundary (Phase B1) — stub it out.
        def __init__(self): self.commit = AsyncMock()
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass

    with patch(
        "backend.jobs.check_milestones.get_session_factory",
        return_value=lambda: _FakeSession(),
    ), patch(
        "backend.jobs.check_milestones.milestone_service.detect_and_record",
        new_callable=AsyncMock,
    ), patch(
        "backend.jobs.check_milestones.milestone_service.get_uncelebrated",
        new_callable=AsyncMock,
        return_value=pending,
    ), patch(
        "backend.jobs.check_milestones.milestone_service.get_celebration_message",
        new_callable=AsyncMock,
        return_value="🎉 Xin chào",
    ), patch(
        "backend.jobs.check_milestones.milestone_service.mark_celebrated",
        mark_celebrated_mock,
    ), patch(
        "backend.jobs.check_milestones.send_message",
        new_callable=AsyncMock,
        return_value={"ok": True},
    ):
        await check_milestones._process_user(user)

    # Cap is 2; only 2 mark_celebrated calls, the 3rd row stays pending.
    assert mark_celebrated_mock.await_count == check_milestones.MAX_MESSAGES_PER_USER_PER_DAY
    assert mark_celebrated_mock.await_count == 2


@pytest.mark.asyncio
async def test_failed_send_leaves_milestone_uncelebrated():
    """send_message returning None must NOT stamp celebrated_at."""
    user = _make_user()
    pending = [_make_pending(MilestoneType.DAYS_7)]

    mark_celebrated_mock = AsyncMock()

    class _FakeSession:
        # Job now owns the commit boundary (Phase B1) — stub it out.
        def __init__(self): self.commit = AsyncMock()
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass

    with patch(
        "backend.jobs.check_milestones.get_session_factory",
        return_value=lambda: _FakeSession(),
    ), patch(
        "backend.jobs.check_milestones.milestone_service.detect_and_record",
        new_callable=AsyncMock,
    ), patch(
        "backend.jobs.check_milestones.milestone_service.get_uncelebrated",
        new_callable=AsyncMock,
        return_value=pending,
    ), patch(
        "backend.jobs.check_milestones.milestone_service.get_celebration_message",
        new_callable=AsyncMock,
        return_value="🎉 Xin chào",
    ), patch(
        "backend.jobs.check_milestones.milestone_service.mark_celebrated",
        mark_celebrated_mock,
    ), patch(
        "backend.jobs.check_milestones.send_message",
        new_callable=AsyncMock,
        return_value=None,  # Telegram API error path
    ):
        await check_milestones._process_user(user)

    mark_celebrated_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_successful_send_marks_celebrated():
    user = _make_user()
    pending = [_make_pending(MilestoneType.DAYS_7)]

    mark_celebrated_mock = AsyncMock()

    class _FakeSession:
        # Job now owns the commit boundary (Phase B1) — stub it out.
        def __init__(self): self.commit = AsyncMock()
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass

    with patch(
        "backend.jobs.check_milestones.get_session_factory",
        return_value=lambda: _FakeSession(),
    ), patch(
        "backend.jobs.check_milestones.milestone_service.detect_and_record",
        new_callable=AsyncMock,
    ), patch(
        "backend.jobs.check_milestones.milestone_service.get_uncelebrated",
        new_callable=AsyncMock,
        return_value=pending,
    ), patch(
        "backend.jobs.check_milestones.milestone_service.get_celebration_message",
        new_callable=AsyncMock,
        return_value="🎉 Xin chào",
    ), patch(
        "backend.jobs.check_milestones.milestone_service.mark_celebrated",
        mark_celebrated_mock,
    ), patch(
        "backend.jobs.check_milestones.send_message",
        new_callable=AsyncMock,
        return_value={"ok": True, "result": {}},
    ):
        await check_milestones._process_user(user)

    mark_celebrated_mock.assert_awaited_once()
