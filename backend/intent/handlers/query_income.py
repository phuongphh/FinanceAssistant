"""Handler for ``query_income`` — list income streams + monthly total."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.formatters.money import format_money_full, format_money_short
from backend.intent.handlers.base import IntentHandler
from backend.intent.intents import IntentResult
from backend.models.user import User
from backend.wealth.models.income_stream import IncomeStream

# Source type → user-facing Vietnamese label (mirrors income_streams
# CHECK constraint values from the Phase 3A spec).
_SOURCE_LABELS = {
    "salary": "Lương",
    "dividend": "Cổ tức",
    "interest": "Lãi tiết kiệm",
    "rental": "Cho thuê",
    "other": "Thu nhập khác",
}

_SOURCE_ICONS = {
    "salary": "💼",
    "dividend": "📊",
    "interest": "🏦",
    "rental": "🏠",
    "other": "💰",
}


class QueryIncomeHandler(IntentHandler):
    async def handle(
        self, intent: IntentResult, user: User, db: AsyncSession
    ) -> str:
        stmt = (
            select(IncomeStream)
            .where(
                IncomeStream.user_id == user.id,
                IncomeStream.is_active.is_(True),
            )
            .order_by(IncomeStream.amount_monthly.desc())
        )
        rows = list((await db.execute(stmt)).scalars().all())

        # Fall back to monthly_income on the user record so users that
        # only set a single salary at onboarding still get a useful reply.
        if not rows:
            return self._fallback_to_user_field(user)

        return self._format(rows, user)

    def _fallback_to_user_field(self, user: User) -> str:
        name = user.display_name or "bạn"
        monthly = getattr(user, "monthly_income", None)
        if monthly:
            return (
                f"💼 Thu nhập của {name} (theo onboarding):\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"Lương: *{format_money_full(monthly)}*/tháng\n\n"
                "Muốn thêm nguồn thu nhập (cổ tức, lãi, cho thuê...) "
                "thì gõ /thunhap nhé."
            )
        return (
            f"{name} chưa thêm nguồn thu nhập nào.\n\n"
            "Mình giúp bạn track thu nhập đa nguồn — gõ /thunhap để bắt đầu."
        )

    def _format(self, streams: list[IncomeStream], user: User) -> str:
        total = sum(Decimal(s.amount_monthly or 0) for s in streams)
        name = user.display_name or "bạn"

        lines = [
            f"💼 Thu nhập hàng tháng của {name}:",
            "━━━━━━━━━━━━━━━━━━━━",
            f"Tổng: *{format_money_full(total)}*/tháng",
            "",
        ]
        for s in streams:
            icon = _SOURCE_ICONS.get(s.source_type, "💰")
            label = _SOURCE_LABELS.get(s.source_type, s.source_type)
            lines.append(
                f"{icon} *{label}* — {s.name}: "
                f"{format_money_short(s.amount_monthly)}/tháng"
            )

        return "\n".join(lines)
