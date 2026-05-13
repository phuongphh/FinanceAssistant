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
    async def handle(self, intent: IntentResult, user: User, db: AsyncSession) -> str:
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

        change = await net_worth_calculator.calculate_change_from_current(
            db,
            user.id,
            breakdown.total,
            period=net_worth_calculator.PERIOD_MONTH,
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

        if style.show_ytd_return:
            ytd = await net_worth_calculator.calculate_ytd_return_from_current(
                db,
                user.id,
                breakdown.total,
                account_created_at=user.created_at,
            )
            if ytd.change_percentage is None:
                lines.append(f"_{ytd.period_label}: —_")
            else:
                sign = "+" if ytd.change_percentage >= 0 else ""
                arrow = "📈" if ytd.change_percentage >= 0 else "📉"
                lines.append(
                    f"_{arrow} {ytd.period_label}: {sign}{ytd.change_percentage:.1f}%_"
                )

        return decorate("\n".join(lines), style)
