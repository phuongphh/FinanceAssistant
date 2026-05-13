"""Tests for ``backend.agent.tools.get_goals``.

Spec § "Phase 3.7 agent can query goals". We assert:
- Registered in default registry.
- Description has ≥5 examples.
- ``include_projection=True`` populates feasibility/required savings.
- ``include_projection=False`` skips the projection compute.
- ``status='completed'`` filters correctly.
- ``limit`` caps result count.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from backend.agent.tools import build_default_registry
from backend.agent.tools.get_goals import GetGoalsTool
from backend.agent.tools.schemas import (
    GetGoalsInput,
    GetGoalsOutput,
    GoalStatusFilter,
)
from backend.models.goal import Goal
from backend.models.user import User


def _user() -> User:
    u = User()
    u.id = uuid.uuid4()
    u.telegram_id = 1
    return u


def _goal(
    *,
    name: str = "Mua xe",
    target: Decimal = Decimal("800000000"),
    current: Decimal = Decimal("100000000"),
    target_date: date | None = None,
    status: str = "active",
    template_id: str | None = "buy_car",
) -> Goal:
    g = Goal()
    g.id = uuid.uuid4()
    g.user_id = uuid.uuid4()
    g.name = name
    g.template_id = template_id
    g.icon = "🚗"
    g.target_amount = target
    g.current_amount = current
    g.target_date = target_date
    g.monthly_savings_required = None
    g.status = status
    g.priority = 5
    g.created_at = datetime.utcnow()
    g.updated_at = datetime.utcnow()
    return g


class TestRegistration:
    def test_in_default_registry(self):
        registry = build_default_registry()
        assert "get_goals" in registry.names()
        assert isinstance(registry.get("get_goals"), GetGoalsTool)

    def test_description_has_5_plus_examples(self):
        desc = GetGoalsTool().description
        assert desc.count("- '") >= 5


@pytest.mark.asyncio
class TestExecute:
    async def test_basic_active_goals_with_projection(self):
        user = _user()
        goals = [
            _goal(name="Mua xe", target_date=date(2030, 1, 1)),
            _goal(name="Du lịch", target=Decimal("50000000")),
        ]
        with patch(
            "backend.agent.tools.get_goals.goal_service.list_goals",
            new=AsyncMock(return_value=goals),
        ), patch(
            "backend.agent.tools.get_goals.goal_projection.get_avg_monthly_savings",
            new=AsyncMock(return_value=Decimal("10000000")),
        ):
            tool = GetGoalsTool()
            result = await tool.execute(GetGoalsInput(), user, db=None)
        assert isinstance(result, GetGoalsOutput)
        assert result.count == 2
        # Goal with target_date should have feasibility set.
        car = next(g for g in result.goals if g.name == "Mua xe")
        assert car.feasibility is not None
        assert car.required_monthly_savings is not None

    async def test_include_projection_false_skips_compute(self):
        user = _user()
        goals = [_goal(target_date=date(2030, 1, 1))]
        with patch(
            "backend.agent.tools.get_goals.goal_service.list_goals",
            new=AsyncMock(return_value=goals),
        ), patch(
            "backend.agent.tools.get_goals.goal_projection.get_avg_monthly_savings",
            new=AsyncMock(),
        ) as savings_mock:
            tool = GetGoalsTool()
            await tool.execute(
                GetGoalsInput(include_projection=False), user, db=None,
            )
        # Service shouldn't be called at all when projection is off.
        savings_mock.assert_not_awaited()

    async def test_status_filter_completed(self):
        user = _user()
        active = _goal(name="Active goal", status="active")
        completed = _goal(name="Done goal", status="completed",
                          current=Decimal("100000000"),
                          target=Decimal("100000000"))
        # Service is called with active_only=False when filter ≠ active.
        with patch(
            "backend.agent.tools.get_goals.goal_service.list_goals",
            new=AsyncMock(return_value=[active, completed]),
        ) as list_mock, patch(
            "backend.agent.tools.get_goals.goal_projection.get_avg_monthly_savings",
            new=AsyncMock(return_value=Decimal("0")),
        ):
            tool = GetGoalsTool()
            result = await tool.execute(
                GetGoalsInput(status=GoalStatusFilter.COMPLETED),
                user, db=None,
            )
        # active_only=False so the list service returned both rows;
        # post-filter narrows to completed only.
        list_call_kwargs = list_mock.await_args.kwargs
        assert list_call_kwargs.get("active_only") is False
        assert result.count == 1
        assert result.goals[0].name == "Done goal"

    async def test_limit_caps_count(self):
        user = _user()
        many = [_goal(name=f"Goal {i}") for i in range(5)]
        with patch(
            "backend.agent.tools.get_goals.goal_service.list_goals",
            new=AsyncMock(return_value=many),
        ), patch(
            "backend.agent.tools.get_goals.goal_projection.get_avg_monthly_savings",
            new=AsyncMock(return_value=Decimal(0)),
        ):
            tool = GetGoalsTool()
            result = await tool.execute(
                GetGoalsInput(limit=2), user, db=None,
            )
        assert result.count == 2

    async def test_empty_user(self):
        user = _user()
        with patch(
            "backend.agent.tools.get_goals.goal_service.list_goals",
            new=AsyncMock(return_value=[]),
        ), patch(
            "backend.agent.tools.get_goals.goal_projection.get_avg_monthly_savings",
            new=AsyncMock(return_value=Decimal(0)),
        ):
            tool = GetGoalsTool()
            result = await tool.execute(GetGoalsInput(), user, db=None)
        assert result.count == 0
        assert result.goals == []
