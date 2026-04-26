"""Tests for threshold_service — income-based storytelling thresholds.

What we pin:

- All four income brackets return the documented (micro, major) pair
- Boundary values (exactly 15tr, 30tr, 60tr) fall into the higher bucket
- Edge cases (None, 0, negative) return the safe defaults
- ``update_user_thresholds`` writes back to ``users.expense_threshold_*``
- ``get_monthly_income`` sums active streams and falls back to legacy field
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.models.user import User
from backend.wealth.services import threshold_service
from backend.wealth.services.threshold_service import (
    DEFAULT_MAJOR,
    DEFAULT_MICRO,
    compute_thresholds,
)


class TestComputeThresholds:
    @pytest.mark.parametrize(
        "income,expected",
        [
            # Bracket 1: < 15tr → (100k, 1tr)
            (Decimal("0"), (DEFAULT_MICRO, DEFAULT_MAJOR)),  # zero → defaults
            (Decimal("1_000_000"), (Decimal("100_000"), Decimal("1_000_000"))),
            (Decimal("10_000_000"), (Decimal("100_000"), Decimal("1_000_000"))),
            (Decimal("14_999_999"), (Decimal("100_000"), Decimal("1_000_000"))),
            # Bracket 2: 15tr - 30tr → (200k, 2tr)
            (Decimal("15_000_000"), (Decimal("200_000"), Decimal("2_000_000"))),
            (Decimal("20_000_000"), (Decimal("200_000"), Decimal("2_000_000"))),
            (Decimal("29_999_999"), (Decimal("200_000"), Decimal("2_000_000"))),
            # Bracket 3: 30tr - 60tr → (300k, 3tr)
            (Decimal("30_000_000"), (Decimal("300_000"), Decimal("3_000_000"))),
            (Decimal("45_000_000"), (Decimal("300_000"), Decimal("3_000_000"))),
            (Decimal("59_999_999"), (Decimal("300_000"), Decimal("3_000_000"))),
            # Bracket 4: 60tr+ → (500k, 5tr)
            (Decimal("60_000_000"), (Decimal("500_000"), Decimal("5_000_000"))),
            (Decimal("100_000_000"), (Decimal("500_000"), Decimal("5_000_000"))),
            (Decimal("500_000_000"), (Decimal("500_000"), Decimal("5_000_000"))),
        ],
    )
    def test_brackets(self, income, expected):
        assert compute_thresholds(income) == expected

    def test_none_returns_defaults(self):
        assert compute_thresholds(None) == (DEFAULT_MICRO, DEFAULT_MAJOR)

    def test_negative_returns_defaults(self):
        assert compute_thresholds(Decimal("-1")) == (DEFAULT_MICRO, DEFAULT_MAJOR)
        assert compute_thresholds(Decimal("-1_000_000")) == (
            DEFAULT_MICRO,
            DEFAULT_MAJOR,
        )

    def test_int_input_works(self):
        assert compute_thresholds(20_000_000) == (
            Decimal("200_000"),
            Decimal("2_000_000"),
        )

    def test_float_input_works(self):
        assert compute_thresholds(45_000_000.0) == (
            Decimal("300_000"),
            Decimal("3_000_000"),
        )

    def test_garbage_returns_defaults(self):
        # The signature is annotated for numeric input; passing nonsense
        # should still degrade gracefully rather than raise.
        assert compute_thresholds("not a number") == (  # type: ignore[arg-type]
            DEFAULT_MICRO,
            DEFAULT_MAJOR,
        )


def _user(monthly_income: Decimal | None = None) -> User:
    u = User()
    u.id = uuid.uuid4()
    u.telegram_id = 100
    u.monthly_income = monthly_income
    u.expense_threshold_micro = 200_000
    u.expense_threshold_major = 2_000_000
    u.created_at = datetime.utcnow()
    return u


class TestGetMonthlyIncome:
    @pytest.mark.asyncio
    async def test_sums_active_streams(self):
        user_id = uuid.uuid4()
        db = MagicMock()
        result = MagicMock()
        result.scalar_one.return_value = Decimal("25_000_000")
        db.execute = AsyncMock(return_value=result)
        db.get = AsyncMock(return_value=None)

        income = await threshold_service.get_monthly_income(db, user_id)
        assert income == Decimal("25_000_000")

    @pytest.mark.asyncio
    async def test_falls_back_to_legacy_monthly_income(self):
        """When income_streams is empty, the legacy field still works."""
        user_id = uuid.uuid4()
        user = _user(monthly_income=Decimal("18_000_000"))
        db = MagicMock()
        result = MagicMock()
        result.scalar_one.return_value = 0
        db.execute = AsyncMock(return_value=result)
        db.get = AsyncMock(return_value=user)

        income = await threshold_service.get_monthly_income(db, user_id)
        assert income == Decimal("18_000_000")

    @pytest.mark.asyncio
    async def test_no_income_returns_zero(self):
        user_id = uuid.uuid4()
        user = _user(monthly_income=None)
        db = MagicMock()
        result = MagicMock()
        result.scalar_one.return_value = 0
        db.execute = AsyncMock(return_value=result)
        db.get = AsyncMock(return_value=user)

        income = await threshold_service.get_monthly_income(db, user_id)
        assert income == Decimal(0)


class TestUpdateUserThresholds:
    @pytest.mark.asyncio
    async def test_writes_thresholds_to_user(self):
        user = _user()
        result = MagicMock()
        result.scalar_one.return_value = Decimal("20_000_000")
        db = MagicMock()
        db.get = AsyncMock(return_value=user)
        db.execute = AsyncMock(return_value=result)
        db.flush = AsyncMock()

        micro, major = await threshold_service.update_user_thresholds(db, user.id)
        assert (micro, major) == (Decimal("200_000"), Decimal("2_000_000"))
        assert user.expense_threshold_micro == 200_000
        assert user.expense_threshold_major == 2_000_000
        db.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_high_income_writes_higher_thresholds(self):
        user = _user()
        result = MagicMock()
        result.scalar_one.return_value = Decimal("80_000_000")
        db = MagicMock()
        db.get = AsyncMock(return_value=user)
        db.execute = AsyncMock(return_value=result)
        db.flush = AsyncMock()

        micro, major = await threshold_service.update_user_thresholds(db, user.id)
        assert (micro, major) == (Decimal("500_000"), Decimal("5_000_000"))
        assert user.expense_threshold_micro == 500_000
        assert user.expense_threshold_major == 5_000_000

    @pytest.mark.asyncio
    async def test_does_not_commit(self):
        """Service flushes; caller commits — boundary contract."""
        user = _user()
        result = MagicMock()
        result.scalar_one.return_value = Decimal("10_000_000")
        db = MagicMock()
        db.get = AsyncMock(return_value=user)
        db.execute = AsyncMock(return_value=result)
        db.flush = AsyncMock()
        db.commit = AsyncMock()

        await threshold_service.update_user_thresholds(db, user.id)
        db.flush.assert_awaited()
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_user_returns_defaults_no_flush(self):
        db = MagicMock()
        db.get = AsyncMock(return_value=None)
        db.flush = AsyncMock()

        micro, major = await threshold_service.update_user_thresholds(
            db, uuid.uuid4()
        )
        assert (micro, major) == (DEFAULT_MICRO, DEFAULT_MAJOR)
        db.flush.assert_not_awaited()
