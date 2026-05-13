"""Unit tests for onboarding_service DB-touching methods.

These setters are thin — they fetch the User and mutate one attribute
— but they are the only write path for onboarding state transitions
so regressions here break the whole flow. Tests mock ``AsyncSession``
to keep them fast and DB-free.

Post Phase B1: services flush-only; the worker/router owns commit.
Tests assert the boundary by checking ``flush`` was called and
``commit`` was NOT.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.bot.personality.onboarding_flow import OnboardingStep
from backend.models.user import User
from backend.services import onboarding_service


def _fake_user(**overrides) -> User:
    u = User()
    u.id = overrides.get("id", uuid.uuid4())
    u.telegram_id = overrides.get("telegram_id", 100)
    u.display_name = overrides.get("display_name")
    u.primary_goal = overrides.get("primary_goal")
    u.onboarding_step = overrides.get("onboarding_step", 0)
    u.onboarding_completed_at = overrides.get("onboarding_completed_at")
    u.onboarding_skipped = overrides.get("onboarding_skipped", False)
    return u


def _mock_session(user: User | None) -> MagicMock:
    """An AsyncSession stub whose .get returns the user; flush and
    commit are awaitable so we can assert the boundary."""
    session = MagicMock()
    session.get = AsyncMock(return_value=user)
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    return session


def _assert_service_owned_flush(db: MagicMock) -> None:
    """Service flushes, caller commits — service must never commit."""
    db.flush.assert_awaited_once()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
class TestSetStep:
    async def test_advances_existing_user(self):
        user = _fake_user(onboarding_step=0)
        db = _mock_session(user)
        await onboarding_service.set_step(db, user.id, OnboardingStep.ASKING_NAME)
        assert user.onboarding_step == int(OnboardingStep.ASKING_NAME)
        _assert_service_owned_flush(db)

    async def test_no_op_when_user_missing(self):
        db = _mock_session(None)
        await onboarding_service.set_step(
            db, uuid.uuid4(), OnboardingStep.WELCOME
        )
        # flush must NOT fire if there's no user to mutate.
        db.flush.assert_not_awaited()
        db.commit.assert_not_awaited()


@pytest.mark.asyncio
class TestSetDisplayName:
    async def test_sets_name(self):
        user = _fake_user()
        db = _mock_session(user)
        await onboarding_service.set_display_name(db, user.id, "Minh")
        assert user.display_name == "Minh"
        _assert_service_owned_flush(db)

    async def test_no_op_when_user_missing(self):
        db = _mock_session(None)
        await onboarding_service.set_display_name(db, uuid.uuid4(), "Minh")
        db.flush.assert_not_awaited()
        db.commit.assert_not_awaited()


@pytest.mark.asyncio
class TestSetPrimaryGoal:
    async def test_sets_goal(self):
        user = _fake_user()
        db = _mock_session(user)
        await onboarding_service.set_primary_goal(db, user.id, "save_more")
        assert user.primary_goal == "save_more"
        _assert_service_owned_flush(db)


@pytest.mark.asyncio
class TestMarkCompleted:
    async def test_stamps_completed_at_and_advances_step(self):
        user = _fake_user(onboarding_step=int(OnboardingStep.FIRST_TRANSACTION))
        db = _mock_session(user)
        before = datetime.now(timezone.utc)
        await onboarding_service.mark_completed(db, user.id)
        after = datetime.now(timezone.utc)

        assert user.onboarding_step == int(OnboardingStep.COMPLETED)
        assert user.onboarding_completed_at is not None
        assert before <= user.onboarding_completed_at <= after
        assert user.onboarding_completed_at.tzinfo is not None  # tz-aware
        _assert_service_owned_flush(db)


@pytest.mark.asyncio
class TestMarkSkipped:
    async def test_sets_skipped_flag(self):
        user = _fake_user(onboarding_skipped=False)
        db = _mock_session(user)
        await onboarding_service.mark_skipped(db, user.id)
        assert user.onboarding_skipped is True
        _assert_service_owned_flush(db)


@pytest.mark.asyncio
class TestIsInFirstTransactionStep:
    async def test_returns_true_when_at_step_4(self):
        user = _fake_user(onboarding_step=int(OnboardingStep.FIRST_TRANSACTION))
        db = _mock_session(user)
        assert await onboarding_service.is_in_first_transaction_step(
            db, user.id
        ) is True

    async def test_returns_false_when_at_other_step(self):
        user = _fake_user(onboarding_step=int(OnboardingStep.ASKING_NAME))
        db = _mock_session(user)
        assert await onboarding_service.is_in_first_transaction_step(
            db, user.id
        ) is False

    async def test_returns_false_when_user_missing(self):
        db = _mock_session(None)
        assert await onboarding_service.is_in_first_transaction_step(
            db, uuid.uuid4()
        ) is False


class TestUserModel:
    """Edge cases for the User helpers that onboarding relies on."""

    def test_is_onboarded_with_tz_naive_completed_at(self):
        # Some test paths may produce naive timestamps — verify the
        # property still treats them as "onboarded".
        u = _fake_user()
        u.onboarding_completed_at = datetime(2026, 4, 22, 9, 0, 0)  # naive
        assert u.is_onboarded is True

    def test_greeting_falls_back_for_whitespace_name(self):
        u = _fake_user(display_name="   ")
        assert u.get_greeting_name() == "bạn"

    def test_greeting_strips_name(self):
        u = _fake_user(display_name="  Trang  ")
        assert u.get_greeting_name() == "Trang"
