"""Handler for ``query_net_worth`` — total + change vs last month."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.formatters.money import format_money_full, format_money_short
from backend.intent.handlers.base import IntentHandler
from backend.intent.intents import IntentResult
from backend.intent.wealth_adapt import decorate, style_for_level
from backend.models.user import User
from backend.wealth.ladder import detect_level
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
                "Tap /themtaisan để mình tính tổng tài sản giúp nhé 🚀"
            )

        # Detect level from the same breakdown we already fetched —
        # avoids an extra round trip from resolve_style().
        level = detect_level(breakdown.total)
        style = style_for_level(level, breakdown.total)

        change = await net_worth_calculator.calculate_change(
            db, user.id, period=net_worth_calculator.PERIOD_MONTH
        )

        name = user.display_name or "bạn"
        lines = [
            f"💰 Tổng tài sản của {name}:",
            f"*{format_money_full(breakdown.total)}*",
        ]
        if style.show_percent_change and change.previous > 0:
            sign = "+" if change.change_absolute >= 0 else ""
            arrow = "📈" if change.change_absolute >= 0 else "📉"
            lines.append(
                f"{arrow} {sign}{format_money_short(change.change_absolute)} "
                f"({sign}{change.change_percentage:.1f}%) so với {change.period_label}"
            )

        if breakdown.asset_count and not style.is_starter:
            lines.append("")
            lines.append(f"_Theo dõi qua {breakdown.asset_count} tài sản_")

        # HNW gets a coarse YTD-style line. We don't have a real YTD
        # calculator yet (Phase 4 dashboard handles that) so we use the
        # year-period approximation from net_worth_calculator.
        if style.show_ytd_return:
            try:
                yearly = await net_worth_calculator.calculate_change(
                    db, user.id, period=net_worth_calculator.PERIOD_YEAR
                )
            except ValueError:
                yearly = None
            if yearly is not None and yearly.previous > 0:
                sign = "+" if yearly.change_percentage >= 0 else ""
                lines.append(
                    f"_Lợi nhuận năm (ước tính): {sign}{yearly.change_percentage:.1f}%_"
                )

        return decorate("\n".join(lines), style)
