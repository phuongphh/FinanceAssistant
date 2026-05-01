"""Handler for ``query_net_worth`` — total + change vs last month."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.formatters.money import format_money_full, format_money_short
from backend.intent.handlers.base import IntentHandler
from backend.intent.intents import IntentResult
from backend.models.user import User
from backend.wealth.services import net_worth_calculator


class QueryNetWorthHandler(IntentHandler):
    async def handle(
        self, intent: IntentResult, user: User, db: AsyncSession
    ) -> str:
        breakdown = await net_worth_calculator.calculate(db, user.id)
        if breakdown.total <= 0:
            name = user.display_name or "bạn"
            return (
                f"💎 {name} chưa có tài sản nào trong hệ thống.\n\n"
                "Tap /themtaisan để mình tính net worth giúp nhé 🚀"
            )

        change = await net_worth_calculator.calculate_change(
            db, user.id, period=net_worth_calculator.PERIOD_MONTH
        )

        name = user.display_name or "bạn"
        lines = [
            f"💰 Tổng tài sản của {name}:",
            "━━━━━━━━━━━━━━━━━━━━",
            f"*{format_money_full(breakdown.total)}*",
        ]
        if change.previous > 0:
            sign = "+" if change.change_absolute >= 0 else ""
            arrow = "📈" if change.change_absolute >= 0 else "📉"
            lines.append(
                f"{arrow} {sign}{format_money_short(change.change_absolute)} "
                f"({sign}{change.change_percentage:.1f}%) so với {change.period_label}"
            )

        if breakdown.asset_count:
            lines.append("")
            lines.append(f"_Theo dõi qua {breakdown.asset_count} tài sản_")

        return "\n".join(lines)
