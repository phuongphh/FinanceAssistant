"""Unit tests for ``backend.wealth.ladder``.

Boundary values are the high-risk path (Starter ↔ YP at 30tr exactly,
YP ↔ Mass Affluent at 200tr, etc.) so we test each one explicitly.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.models.user import User
from backend.wealth.ladder import (
    WealthLevel,
    detect_level,
    next_milestone,
    update_user_level,
)


class TestDetectLevel:
    @pytest.mark.parametrize(
        "amount,expected",
        [
            (0, WealthLevel.STARTER),
            (1_000_000, WealthLevel.STARTER),
            (29_999_999, WealthLevel.STARTER),
            (30_000_000, WealthLevel.YOUNG_PROFESSIONAL),
            (100_000_000, WealthLevel.YOUNG_PROFESSIONAL),
            (199_999_999, WealthLevel.YOUNG_PROFESSIONAL),
            (200_000_000, WealthLevel.MASS_AFFLUENT),
            (500_000_000, WealthLevel.MASS_AFFLUENT),
            (999_999_999, WealthLevel.MASS_AFFLUENT),
            (1_000_000_000, WealthLevel.HIGH_NET_WORTH),
            (5_000_000_000, WealthLevel.HIGH_NET_WORTH),
        ],
    )
    def test_boundary_values(self, amount, expected):
        assert detect_level(Decimal(amount)) == expected

    def test_handles_none(self):
        assert detect_level(None) == WealthLevel.STARTER

    def test_handles_int_and_float(self):
        # detect_level should be lenient about numeric types.
        assert detect_level(50_000_000) == WealthLevel.YOUNG_PROFESSIONAL
        assert detect_level(50_000_000.0) == WealthLevel.YOUNG_PROFESSIONAL


class TestNextMilestone:
    def test_starter_target_is_30m(self):
        target, level = next_milestone(Decimal("5_000_000"))
        assert target == Decimal("30_000_000")
        assert level == WealthLevel.YOUNG_PROFESSIONAL

    def test_intermediate_yp_target_is_100m(self):
        target, _ = next_milestone(Decimal("50_000_000"))
        assert target == Decimal("100_000_000")

    def test_late_yp_target_is_200m(self):
        target, level = next_milestone(Decimal("150_000_000"))
        assert target == Decimal("200_000_000")
        assert level == WealthLevel.MASS_AFFLUENT

    def test_mass_affluent_500m_target(self):
        target, _ = next_milestone(Decimal("300_000_000"))
        assert target == Decimal("500_000_000")

    def test_late_mass_affluent_to_1b(self):
        target, level = next_milestone(Decimal("700_000_000"))
        assert target == Decimal("1_000_000_000")
        assert level == WealthLevel.HIGH_NET_WORTH

    def test_hnw_climbs_by_billion(self):
        target, level = next_milestone(Decimal("1_500_000_000"))
        assert target == Decimal("2_000_000_000")
        assert level == WealthLevel.HIGH_NET_WORTH

    def test_hnw_exact_billion_climbs_to_next(self):
        target, _ = next_milestone(Decimal("3_000_000_000"))
        assert target == Decimal("4_000_000_000")


@pytest.mark.asyncio
class TestUpdateUserLevel:
    async def test_persists_new_level(self):
        user = User()
        user.id = uuid.uuid4()
        user.wealth_level = None

        db = MagicMock()
        db.get = AsyncMock(return_value=user)
        db.flush = AsyncMock()

        new_level = await update_user_level(
            db, user.id, Decimal("50_000_000")
        )
        assert new_level == WealthLevel.YOUNG_PROFESSIONAL
        assert user.wealth_level == "young_prof"
        db.flush.assert_awaited_once()

    async def test_returns_none_when_unchanged(self):
        user = User()
        user.id = uuid.uuid4()
        user.wealth_level = "young_prof"

        db = MagicMock()
        db.get = AsyncMock(return_value=user)
        db.flush = AsyncMock()

        result = await update_user_level(db, user.id, Decimal("50_000_000"))
        assert result is None
        db.flush.assert_not_awaited()

    async def test_returns_none_when_user_missing(self):
        db = MagicMock()
        db.get = AsyncMock(return_value=None)
        db.flush = AsyncMock()
        result = await update_user_level(
            db, uuid.uuid4(), Decimal("50_000_000")
        )
        assert result is None
