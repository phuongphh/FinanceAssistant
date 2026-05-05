"""Handlers for ``query_goals`` and ``query_goal_progress``."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.formatters.money import format_money_full, format_money_short
from backend.intent.handlers.base import IntentHandler
from backend.intent.intents import IntentResult
from backend.models.goal import Goal
from backend.models.user import User
from backend.services import goal_service


def _progress_bar(pct: float, width: int = 10) -> str:
    """Unicode progress bar — full block for completed segments."""
    pct = max(0.0, min(100.0, pct))
    filled = int(round(pct / 100 * width))
    return "█" * filled + "░" * (width - filled)


def _format_goal_line(goal: Goal) -> str:
    target = Decimal(goal.target_amount or 0)
    current = Decimal(goal.current_amount or 0)
    pct = float(current / target * 100) if target > 0 else 0.0
    bar = _progress_bar(pct)
    return (
        f"🎯 *{goal.goal_name}*\n"
        f"   {bar} {pct:.0f}%\n"
        f"   {format_money_short(current)} / {format_money_short(target)}"
    )


class QueryGoalsHandler(IntentHandler):
    async def handle(
        self, intent: IntentResult, user: User, db: AsyncSession
    ) -> str:
        goals = await goal_service.list_goals(db, user.id, active_only=True)
        name = user.display_name or "bạn"
        if not goals:
            return (
                f"{name} chưa đặt mục tiêu nào 🌱\n\n"
                "Đặt mục tiêu giúp track tiến độ rõ ràng hơn — gõ /muctieu để bắt đầu."
            )
        lines = [
            f"🎯 Mục tiêu của {name}:",
            "",
        ]
        for g in goals:
            lines.append(_format_goal_line(g))
            lines.append("")
        return "\n".join(lines).rstrip()


class QueryGoalProgressHandler(IntentHandler):
    """Lookup-by-name; falls back to listing all goals if name is missing
    or doesn't match anything."""

    async def handle(
        self, intent: IntentResult, user: User, db: AsyncSession
    ) -> str:
        goal_name = (intent.parameters.get("goal_name") or "").strip()
        goals = await goal_service.list_goals(db, user.id, active_only=True)
        if not goals:
            name = user.display_name or "bạn"
            return (
                f"{name} chưa có mục tiêu nào để track 🌱\n\n"
                "Tap /muctieu để đặt mục tiêu đầu tiên."
            )

        match = self._best_match(goals, goal_name) if goal_name else None
        if match is None:
            # No goal matched — show the list and let the user clarify.
            handler = QueryGoalsHandler()
            return await handler.handle(intent, user, db)

        return self._format_progress(match, user)

    def _best_match(self, goals: list[Goal], needle: str) -> Goal | None:
        n = needle.lower()
        for g in goals:
            if g.goal_name.lower() == n:
                return g
        for g in goals:
            if n in g.goal_name.lower() or g.goal_name.lower() in n:
                return g
        return None

    def _format_progress(self, goal: Goal, user: User) -> str:
        target = Decimal(goal.target_amount or 0)
        current = Decimal(goal.current_amount or 0)
        remaining = max(target - current, Decimal(0))
        pct = float(current / target * 100) if target > 0 else 0.0
        bar = _progress_bar(pct, width=12)

        lines = [
            f"🎯 *{goal.goal_name}*",
            f"{bar} {pct:.0f}%",
            "",
            f"Đã có: *{format_money_full(current)}*",
            f"Mục tiêu: *{format_money_full(target)}*",
        ]
        if remaining > 0:
            lines.append(f"Còn lại: *{format_money_short(remaining)}*")
            if goal.deadline:
                lines.append(f"Hạn: {goal.deadline.strftime('%d/%m/%Y')}")
        else:
            lines.append("✅ Hoàn thành rồi! Chúc mừng 🎉")
        return "\n".join(lines)
