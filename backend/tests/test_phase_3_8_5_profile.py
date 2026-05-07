from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.models.user import User
from backend.profile.handlers.profile_menu import render_profile
from backend.profile.models.user_profile import UserProfile
from backend.profile.services.stats_aggregator import ProfileStatsAggregator
from backend.profile.services.wealth_level_mapper import WealthLevelMapper


def _scalar(value):
    result = MagicMock()
    result.scalar.return_value = value
    result.scalar_one_or_none.return_value = value
    return result


def _scalars(values):
    scalars = MagicMock()
    scalars.all.return_value = values
    result = MagicMock()
    result.scalars.return_value = scalars
    return result


def test_wealth_level_starter():
    level = WealthLevelMapper().get_level(Decimal("15000000"))
    assert level["name_vn"] == "Khởi Đầu"


def test_wealth_level_boundary_30tr():
    level = WealthLevelMapper().get_level(Decimal("30000000"))
    assert level["name_vn"] == "Trẻ Năng Động"


def test_wealth_progress_halfway_to_next():
    progress = WealthLevelMapper().get_progress_to_next(Decimal("15000000"))
    assert 49 <= progress["progress_pct"] <= 51
    assert progress["next_level_name"] == "Trẻ Năng Động"


@pytest.mark.asyncio
async def test_aggregate_new_user_defaults_gracefully():
    user = User()
    user.id = uuid.uuid4()
    user.created_at = datetime.now(timezone.utc)
    db = MagicMock()
    db.get = AsyncMock(return_value=user)
    db.execute = AsyncMock(side_effect=[
        _scalar(0),  # asset types
        _scalar(0),  # transactions total
        _scalar(0),  # transactions month
        _scalar(0),  # goals active
        _scalar(0),  # goals completed
        _scalar(0),  # briefing reads
        _scalars([]),  # activity days
        _scalar(None),  # first snapshot
    ])

    with patch("backend.profile.services.stats_aggregator.net_worth_calculator.calculate", AsyncMock(return_value=SimpleNamespace(total=Decimal("0")))):
        stats = await ProfileStatsAggregator().aggregate(db, user.id)

    assert stats["account_age_days"] == 0
    assert stats["wealth_level"]["name_vn"] == "Khởi Đầu"
    assert stats["current_streak"] == 1
    assert stats["asset_types_count"] == 0


@pytest.mark.asyncio
async def test_streak_breaks_after_gap():
    aggregator = ProfileStatsAggregator()
    with patch.object(aggregator, "_activity_days", AsyncMock(return_value=[])):
        assert await aggregator._compute_streak(MagicMock(), uuid.uuid4()) == 1


def test_render_profile_includes_vn_level_and_stats():
    profile = UserProfile(user_id=uuid.uuid4(), display_name="Phương")
    user = User()
    user.id = profile.user_id
    user.display_name = "Telegram Phương"
    stats = {
        "account_age_days": 12,
        "net_worth": Decimal("300000000"),
        "wealth_level": WealthLevelMapper().get_level(Decimal("300000000")),
        "wealth_progress": WealthLevelMapper().get_progress_to_next(Decimal("300000000")),
        "asset_types_count": 3,
        "transaction_count_total": 40,
        "transaction_count_this_month": 8,
        "goals_active": 2,
        "goals_completed": 1,
        "briefing_read_count": 5,
        "current_streak": 4,
        "net_worth_change_pct": 12.5,
    }

    text = render_profile(profile, user, stats)

    assert "Phương" in text
    assert "💎" in text
    assert "Trung Lưu Vững" in text
    assert "Tinh Hoa" in text
    assert "8" in text
