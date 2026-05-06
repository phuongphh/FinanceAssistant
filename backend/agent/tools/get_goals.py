"""``get_goals`` tool — Phase 3.8 Epic 5 (success criterion: "Phase
3.7 agent can query goals").

Wraps ``goal_service.list_goals`` + ``goal_projection.project_goal_
with_savings`` so the LLM can answer:

- "mục tiêu của tôi"
- "tiến độ đạt mục tiêu"
- "cần bao lâu để mua xe?"
- "lộ trình đạt mục tiêu"
- "mục tiêu nào sắp hoàn thành?"
- "mục tiêu đã đạt được"   (status=completed)

Output items carry the projection inline so the LLM doesn't need a
second tool call to format "cần 33tr/tháng".
"""
from __future__ import annotations

from decimal import Decimal
from typing import Type

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent.tools.base import Tool
from backend.agent.tools.schemas import (
    GetGoalsInput,
    GetGoalsOutput,
    GoalProjectionItem,
)
from backend.models.user import User
from backend.services import goal_projection, goal_service


class GetGoalsTool(Tool):
    @property
    def name(self) -> str:
        return "get_goals"

    @property
    def description(self) -> str:
        return (
            "Retrieve the user's goals with progress + projection. "
            "Use for ANY query about goals — list, progress, ETA, "
            "feasibility, monthly savings required.\n"
            "\n"
            "Each output item carries:\n"
            "- progress_pct (0-100)\n"
            "- remaining_amount (VND still needed)\n"
            "- months_remaining (when target_date is known)\n"
            "- required_monthly_savings (when target_date is known)\n"
            "- feasibility band (easy / feasible / stretch / "
            "ambitious / needs_revision / unknown)\n"
            "- estimated_completion_date (when goal is open-ended)\n"
            "\n"
            "Examples (Vietnamese query → tool call):\n"
            "- 'mục tiêu của tôi' → {} (no filter)\n"
            "- 'tiến độ đạt mục tiêu' → {} (default; show progress)\n"
            "- 'cần bao lâu để đạt mục tiêu mua xe?' → {} (filter by\n"
            "  name in formatter, tool returns all goals)\n"
            "- 'mục tiêu đã đạt được' → {status: 'completed'}\n"
            "- 'mục tiêu hàng đầu' → {limit: 1}\n"
            "- 'lộ trình đạt mục tiêu' → {} (response uses notes +\n"
            "  feasibility for the path).\n"
            "\n"
            "When formatting, lead with feasibility — users want to "
            "know if their plan is realistic before the dollar amount. "
            "If feasibility=needs_revision, surface the supportive "
            "alternatives from notes."
        )

    @property
    def input_schema(self) -> Type[BaseModel]:
        return GetGoalsInput

    @property
    def output_schema(self) -> Type[BaseModel]:
        return GetGoalsOutput

    async def execute(
        self,
        input_data: GetGoalsInput,
        user: User,
        db: AsyncSession,
    ) -> GetGoalsOutput:
        # ``active_only=False`` when the caller asked for a non-active
        # status; we then post-filter by the requested status. The
        # alternative (passing the status into list_goals) would
        # require widening that service's signature for a code path
        # only the agent uses.
        active_only = (
            input_data.status is None
            or input_data.status.value == "active"
        )
        goals = await goal_service.list_goals(
            db, user.id, active_only=active_only,
        )
        if input_data.status is not None and not active_only:
            goals = [g for g in goals if g.status == input_data.status.value]

        if not input_data.include_projection:
            items = [self._item_no_projection(g) for g in goals]
        else:
            avg_savings = await goal_projection.get_avg_monthly_savings(
                db, user.id,
            )
            items = [
                self._item_with_projection(g, avg_savings) for g in goals
            ]

        if input_data.limit is not None:
            items = items[: input_data.limit]

        return GetGoalsOutput(goals=items, count=len(items))

    def _item_no_projection(self, goal) -> GoalProjectionItem:
        target = Decimal(goal.target_amount or 0)
        current = Decimal(goal.current_amount or 0)
        return GoalProjectionItem(
            goal_id=goal.id,
            name=goal.name,
            icon=goal.icon,
            template_id=goal.template_id,
            target_amount=target,
            current_amount=current,
            target_date=goal.target_date,
            progress_pct=goal.progress_pct,
            remaining_amount=goal.remaining_amount,
            status=goal.status,
            priority=goal.priority,
        )

    def _item_with_projection(
        self, goal, avg_savings: Decimal,
    ) -> GoalProjectionItem:
        proj = goal_projection.project_goal_with_savings(goal, avg_savings)
        return GoalProjectionItem(
            goal_id=goal.id,
            name=goal.name,
            icon=goal.icon,
            template_id=goal.template_id,
            target_amount=Decimal(goal.target_amount or 0),
            current_amount=Decimal(goal.current_amount or 0),
            target_date=goal.target_date,
            progress_pct=proj.current_progress_pct,
            remaining_amount=proj.remaining_amount,
            status=goal.status,
            priority=goal.priority,
            months_remaining=proj.months_remaining,
            required_monthly_savings=proj.required_monthly_savings,
            feasibility=(
                proj.feasibility
                if proj.feasibility is not None else None
            ),
            avg_monthly_savings=proj.avg_monthly_savings,
            estimated_completion_date=proj.estimated_completion_date,
            notes=list(proj.notes),
        )
