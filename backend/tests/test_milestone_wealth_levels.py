"""Tests for wealth-level milestone detection (Issue #155).

Covers ``milestone_service._check_wealth_level_changes`` and the
wealth-level placeholders added to ``_render_context``. Uses the same
MagicMock + ``_fake_execute_rows`` pattern as ``test_milestone_detection``
so the test reads consistently with siblings.

The key behaviours under test:
- Up: starter→YP fires UP_YP only.
- Down: highest_ever YP, current Starter → fires DOWN_STARTER.
- No-change: stays in same level → empty list.
- Yo-yo dedup: re-crossing a boundary already celebrated → no duplicate
  (driven by the ``existing`` set the helper passes to ``_create_if_missing``).
- HNW guard: descending from HNW back to MA fires DOWN_MASS_AFFLUENT
  (no DOWN_HNW exists, that's the point).
- Render: ``{level_label}``, ``{level_full}``, ``{next_target}``,
  ``{next_level_label}`` populate from the milestone's ``extra`` dict.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.models.user_milestone import MilestoneType, UserMilestone
from backend.services import milestone_service
from backend.wealth import ladder


def _fake_user():
    u = MagicMock()
    u.id = uuid.uuid4()
    u.display_name = "Minh"
    u.get_greeting_name.return_value = "Minh"
    return u


def _fake_breakdown(total: Decimal):
    b = MagicMock()
    b.total = total
    return b


def _fake_execute_rows(rows: list[tuple]):
    result = MagicMock()
    result.all.return_value = rows
    result.rowcount = 1  # default: insert succeeds
    return result


def _fake_execute_conflict():
    """Mimic ON CONFLICT DO NOTHING swallowing the insert."""
    result = MagicMock()
    result.all.return_value = []
    result.rowcount = 0
    return result


# -- _check_wealth_level_changes -------------------------------------

@pytest.mark.asyncio
class TestCheckWealthLevelChanges:
    async def test_returns_empty_when_user_missing(self):
        db = MagicMock()
        db.get = AsyncMock(return_value=None)
        out = await milestone_service._check_wealth_level_changes(
            db, uuid.uuid4()
        )
        assert out == []

    async def test_starter_at_zero_no_milestone(self):
        """Fresh account, net worth 0 → still starter, no transition."""
        user = _fake_user()
        db = MagicMock()
        db.get = AsyncMock(return_value=user)
        db.execute = AsyncMock(return_value=_fake_execute_rows([]))

        with patch.object(
            milestone_service, "calculate_net_worth",
            AsyncMock(return_value=_fake_breakdown(Decimal("0"))),
        ):
            out = await milestone_service._check_wealth_level_changes(
                db, user.id
            )
        assert out == []

    async def test_starter_to_young_prof_fires_up(self):
        user = _fake_user()
        db = MagicMock()
        db.get = AsyncMock(return_value=user)
        # No existing wealth milestones.
        db.execute = AsyncMock(return_value=_fake_execute_rows([]))

        with patch.object(
            milestone_service, "calculate_net_worth",
            AsyncMock(return_value=_fake_breakdown(Decimal("50_000_000"))),
        ):
            out = await milestone_service._check_wealth_level_changes(
                db, user.id
            )
        assert len(out) == 1
        assert out[0].milestone_type == MilestoneType.WEALTH_LEVEL_UP_YOUNG_PROF
        assert out[0].extra["new_level"] == "young_prof"
        # next_milestone(50tr) = (100tr, YP) — sub-milestone within band.
        assert out[0].extra["next_target_amount"] == "100000000"
        assert out[0].extra["next_level"] == "young_prof"

    async def test_jump_two_bands_fires_only_destination(self):
        """Asset entry takes user from 0 to 500tr (Mass Affluent)
        without recording an intermediate Young Prof step. We only
        celebrate the band the user is *now* in."""
        user = _fake_user()
        db = MagicMock()
        db.get = AsyncMock(return_value=user)
        db.execute = AsyncMock(return_value=_fake_execute_rows([]))

        with patch.object(
            milestone_service, "calculate_net_worth",
            AsyncMock(return_value=_fake_breakdown(Decimal("500_000_000"))),
        ):
            out = await milestone_service._check_wealth_level_changes(
                db, user.id
            )
        assert len(out) == 1
        assert (
            out[0].milestone_type
            == MilestoneType.WEALTH_LEVEL_UP_MASS_AFFLUENT
        )

    async def test_down_to_starter_fires_after_having_been_yp(self):
        """User previously hit YP (UP_YP exists), now back to <30tr."""
        user = _fake_user()
        db = MagicMock()
        db.get = AsyncMock(return_value=user)
        db.execute = AsyncMock(return_value=_fake_execute_rows(
            [(MilestoneType.WEALTH_LEVEL_UP_YOUNG_PROF,)]
        ))

        with patch.object(
            milestone_service, "calculate_net_worth",
            AsyncMock(return_value=_fake_breakdown(Decimal("20_000_000"))),
        ):
            out = await milestone_service._check_wealth_level_changes(
                db, user.id
            )
        assert len(out) == 1
        assert out[0].milestone_type == MilestoneType.WEALTH_LEVEL_DOWN_STARTER
        assert out[0].extra["new_level"] == "starter"

    async def test_down_from_hnw_fires_down_mass_affluent(self):
        """No DOWN_HNW exists by design — descending from HNW lands as
        a DOWN milestone for the level the user is *now* in."""
        user = _fake_user()
        db = MagicMock()
        db.get = AsyncMock(return_value=user)
        # User was HNW at some point.
        db.execute = AsyncMock(return_value=_fake_execute_rows([
            (MilestoneType.WEALTH_LEVEL_UP_YOUNG_PROF,),
            (MilestoneType.WEALTH_LEVEL_UP_MASS_AFFLUENT,),
            (MilestoneType.WEALTH_LEVEL_UP_HNW,),
        ]))

        with patch.object(
            milestone_service, "calculate_net_worth",
            AsyncMock(return_value=_fake_breakdown(Decimal("700_000_000"))),
        ):
            out = await milestone_service._check_wealth_level_changes(
                db, user.id
            )
        assert len(out) == 1
        assert (
            out[0].milestone_type
            == MilestoneType.WEALTH_LEVEL_DOWN_MASS_AFFLUENT
        )

    async def test_no_change_when_at_same_band(self):
        """Already celebrated YP, still in YP band → nothing new."""
        user = _fake_user()
        db = MagicMock()
        db.get = AsyncMock(return_value=user)
        db.execute = AsyncMock(return_value=_fake_execute_rows([
            (MilestoneType.WEALTH_LEVEL_UP_YOUNG_PROF,),
        ]))

        with patch.object(
            milestone_service, "calculate_net_worth",
            AsyncMock(return_value=_fake_breakdown(Decimal("80_000_000"))),
        ):
            out = await milestone_service._check_wealth_level_changes(
                db, user.id
            )
        assert out == []

    async def test_yoyo_dedup_skips_second_up_celebration(self):
        """User already has DOWN_STARTER recorded from a previous yo-yo;
        re-crossing back up to YP fires nothing (UP_YP also recorded)."""
        user = _fake_user()
        db = MagicMock()
        db.get = AsyncMock(return_value=user)
        db.execute = AsyncMock(return_value=_fake_execute_rows([
            (MilestoneType.WEALTH_LEVEL_UP_YOUNG_PROF,),
            (MilestoneType.WEALTH_LEVEL_DOWN_STARTER,),
        ]))

        with patch.object(
            milestone_service, "calculate_net_worth",
            AsyncMock(return_value=_fake_breakdown(Decimal("40_000_000"))),
        ):
            out = await milestone_service._check_wealth_level_changes(
                db, user.id
            )
        # Highest_ever = YP, current = YP → no transition fires.
        assert out == []

    async def test_yoyo_down_dedup_skips_second_down(self):
        """Already celebrated DOWN_STARTER once. User went up to YP,
        and is now back down to Starter again. The DOWN milestone
        does not double-fire."""
        user = _fake_user()
        db = MagicMock()
        db.get = AsyncMock(return_value=user)
        # Existing rows include both the UP_YP and DOWN_STARTER from last cycle.
        db.execute = AsyncMock(return_value=_fake_execute_conflict())
        db.execute.return_value.all.return_value = [
            (MilestoneType.WEALTH_LEVEL_UP_YOUNG_PROF,),
            (MilestoneType.WEALTH_LEVEL_DOWN_STARTER,),
        ]

        with patch.object(
            milestone_service, "calculate_net_worth",
            AsyncMock(return_value=_fake_breakdown(Decimal("10_000_000"))),
        ):
            out = await milestone_service._check_wealth_level_changes(
                db, user.id
            )
        # _create_if_missing returns None on conflict → empty list.
        assert out == []


# -- _render_context wealth placeholders -----------------------------

class TestRenderContextWealthPlaceholders:
    def test_populates_level_and_next_target(self):
        user = _fake_user()
        milestone = UserMilestone(
            user_id=user.id,
            milestone_type=MilestoneType.WEALTH_LEVEL_UP_YOUNG_PROF,
            extra={
                "new_level": "young_prof",
                "next_target_amount": "100000000",
                "next_level": "young_prof",
            },
        )
        ctx = milestone_service._render_context(milestone, user)
        assert ctx["level_label"] == "Kho thóc"
        assert ctx["level_full"] == "Có chút tiết kiệm"
        # format_money_full of 100M
        assert "100" in ctx["next_target"]
        assert ctx["next_level_label"] == "Kho thóc"

    def test_blank_placeholders_for_non_wealth_milestones(self):
        """Existing time/streak templates don't reference wealth keys —
        but the dict must include them so str.format never KeyErrors
        if we add a placeholder later."""
        user = _fake_user()
        milestone = UserMilestone(
            user_id=user.id,
            milestone_type=MilestoneType.DAYS_7,
            extra={"days": 7},
        )
        ctx = milestone_service._render_context(milestone, user)
        assert ctx["level_label"] == ""
        assert ctx["next_target"] == ""

    def test_unknown_level_value_does_not_crash(self):
        """Defensive: if extra contains a stale enum value, render
        should fall back to empty rather than raise ValueError."""
        user = _fake_user()
        milestone = UserMilestone(
            user_id=user.id,
            milestone_type=MilestoneType.WEALTH_LEVEL_UP_YOUNG_PROF,
            extra={"new_level": "ghost_tier"},
        )
        ctx = milestone_service._render_context(milestone, user)
        assert ctx["level_label"] == ""


# -- ladder.format_level / LEVEL_LABELS ------------------------------

class TestLadderLabels:
    def test_short_labels(self):
        assert ladder.format_level(ladder.WealthLevel.STARTER, "short") == "Trồng lúa"
        assert ladder.format_level(
            ladder.WealthLevel.YOUNG_PROFESSIONAL, "short"
        ) == "Kho thóc"
        assert ladder.format_level(
            ladder.WealthLevel.MASS_AFFLUENT, "short"
        ) == "Phú hộ"
        assert ladder.format_level(
            ladder.WealthLevel.HIGH_NET_WORTH, "short"
        ) == "Vương giả"

    def test_full_labels(self):
        assert ladder.format_level(
            ladder.WealthLevel.STARTER, "full"
        ) == "Bắt đầu tích luỹ"
        assert ladder.format_level(
            ladder.WealthLevel.HIGH_NET_WORTH, "full"
        ) == "Giàu sang phú quý"

    def test_level_order_monotonic(self):
        """Sanity-check that LEVEL_ORDER matches the band thresholds —
        if someone reorders the enum without updating LEVEL_ORDER, the
        index() lookups in _check_wealth_level_changes silently break."""
        assert ladder.LEVEL_ORDER[0] == ladder.WealthLevel.STARTER
        assert ladder.LEVEL_ORDER[-1] == ladder.WealthLevel.HIGH_NET_WORTH
        for i, level in enumerate(ladder.LEVEL_ORDER):
            assert ladder.LEVEL_ORDER.index(level) == i
