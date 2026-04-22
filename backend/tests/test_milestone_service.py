"""Tests for the milestone service.

Covers:
- YAML integrity: every MilestoneType code has at least one message.
- Placeholder rendering: {name}, {days}, {count}, {amount} all resolve.
- Missing-template path: returns empty string, does not raise.
- Graceful degradation when a variation references a missing key.
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from backend.models.user import User
from backend.models.user_milestone import MilestoneType, UserMilestone
from backend.services import milestone_service


def _make_user(name: str | None = "Minh") -> User:
    u = User()
    u.id = uuid.uuid4()
    u.telegram_id = 123
    u.display_name = name
    u.onboarding_skipped = False
    u.onboarding_completed_at = None
    return u


def _make_milestone(m_type: str, extra: dict | None = None) -> UserMilestone:
    m = UserMilestone()
    m.id = uuid.uuid4()
    m.user_id = uuid.uuid4()
    m.milestone_type = m_type
    m.extra = extra or {}
    return m


class TestYamlIntegrity:
    def test_every_milestone_type_has_at_least_one_variation(self):
        milestone_service.reload_messages_for_tests()
        msgs = milestone_service._load_messages()
        for code in MilestoneType.all():
            assert code in msgs, f"YAML missing milestone type: {code}"
            assert isinstance(msgs[code], list) and len(msgs[code]) >= 1

    def test_yaml_keys_do_not_contain_unknown_types(self):
        milestone_service.reload_messages_for_tests()
        msgs = milestone_service._load_messages()
        known = set(MilestoneType.all())
        for key in msgs:
            assert key in known, f"Unknown milestone key in YAML: {key}"


class TestGetCelebrationMessage:
    @pytest.mark.asyncio
    async def test_renders_name_placeholder(self):
        milestone_service.reload_messages_for_tests()
        user = _make_user("Trang")
        m = _make_milestone(MilestoneType.FIRST_TRANSACTION)
        msg = await milestone_service.get_celebration_message(m, user)
        assert "Trang" in msg
        assert "{name}" not in msg

    @pytest.mark.asyncio
    async def test_renders_days_placeholder(self):
        milestone_service.reload_messages_for_tests()
        user = _make_user("Minh")
        m = _make_milestone(MilestoneType.DAYS_7, {"days": 7, "count": 12})
        # Force a deterministic variation so this test is stable.
        with patch(
            "backend.services.milestone_service.random.choice",
            side_effect=lambda xs: xs[0],
        ):
            msg = await milestone_service.get_celebration_message(m, user)
        # Variation 0 of days_7 includes {count}
        assert "12" in msg

    @pytest.mark.asyncio
    async def test_falls_back_to_default_name(self):
        milestone_service.reload_messages_for_tests()
        user = _make_user(None)
        m = _make_milestone(MilestoneType.DAYS_7, {"days": 7, "count": 3})
        msg = await milestone_service.get_celebration_message(m, user)
        assert "bạn" in msg

    @pytest.mark.asyncio
    async def test_unknown_type_returns_empty_string(self):
        milestone_service.reload_messages_for_tests()
        user = _make_user()
        m = _make_milestone("__not_a_real_type__")
        msg = await milestone_service.get_celebration_message(m, user)
        assert msg == ""

    @pytest.mark.asyncio
    async def test_amount_placeholder_formatted_as_vnd(self):
        milestone_service.reload_messages_for_tests()
        user = _make_user("Lan")
        # Use days_30 which has {amount} in variation 0.
        m = _make_milestone(
            MilestoneType.DAYS_30,
            {"days": 30, "count": 80, "amount": 5_200_000},
        )
        with patch(
            "backend.services.milestone_service.random.choice",
            side_effect=lambda xs: xs[0],
        ):
            msg = await milestone_service.get_celebration_message(m, user)
        # format_money_full adds 'đ' suffix and thousand separators.
        assert "5.200.000" in msg or "5,200,000" in msg
        assert "đ" in msg


class TestRenderContextDefaults:
    def test_missing_extra_does_not_raise(self):
        milestone_service.reload_messages_for_tests()
        user = _make_user("Hoa")
        m = _make_milestone(MilestoneType.FIRST_TRANSACTION)
        m.extra = None  # explicitly no metadata
        ctx = milestone_service._render_context(m, user)
        assert ctx["name"] == "Hoa"
        assert ctx["days"] == 0
        assert ctx["count"] == 0
        assert ctx["amount"] == ""
