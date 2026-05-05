"""Handler for ``query_portfolio`` — stocks/funds only with current value."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.formatters.money import format_money_full, format_money_short
from backend.intent.handlers.base import IntentHandler
from backend.intent.intents import IntentResult
from backend.intent.wealth_adapt import LevelStyle, decorate, resolve_style
from backend.models.user import User
from backend.wealth.asset_types import get_quantity_unit
from backend.wealth.services import asset_service


class QueryPortfolioHandler(IntentHandler):
    async def handle(
        self, intent: IntentResult, user: User, db: AsyncSession
    ) -> str:
        # Stock + fund + ETF — all live in the ``stock`` asset_type with
        # subtype distinguishing them. The wealth schema (Phase 3A) does
        # not have a separate asset_type for funds.
        stocks = await asset_service.get_user_assets(
            db, user.id, asset_type="stock"
        )
        if not stocks:
            return self._empty(user)

        style = await resolve_style(db, user)
        return decorate(self._format(stocks, user, style=style), style)

    def _empty(self, user: User) -> str:
        name = user.display_name or "bạn"
        return (
            f"📈 {name} chưa có cổ phiếu / quỹ nào trong portfolio.\n\n"
            "Thêm vào nhanh qua /themtaisan nhé."
        )

    def _format(self, stocks, user: User, *, style: LevelStyle) -> str:
        # Sort by current value desc — biggest holdings first.
        ordered = sorted(
            stocks,
            key=lambda a: Decimal(a.current_value or 0),
            reverse=True,
        )
        total = sum(Decimal(a.current_value or 0) for a in ordered)
        name = user.display_name or "bạn"

        lines = [
            f"📈 Danh mục đầu tư của {name}:",
            f"Tổng giá trị: *{format_money_full(total)}*",
            "",
        ]
        for asset in ordered:
            ticker = (asset.extra or {}).get("ticker") or asset.name
            quantity = (asset.extra or {}).get("quantity")
            unit = get_quantity_unit(asset.asset_type, asset.subtype)
            qty_str = f" ({quantity:g} {unit})" if isinstance(quantity, (int, float)) else ""
            value = format_money_short(asset.current_value)
            # Hide P&L percentage for Starter — too much information for
            # a user with their first few thousand VND in stocks.
            if style.show_pnl_pct:
                pnl_pct = asset.gain_loss_pct
                if pnl_pct is None:
                    pnl_str = ""
                else:
                    arrow = "🟢" if pnl_pct >= 0 else "🔴"
                    sign = "+" if pnl_pct >= 0 else ""
                    pnl_str = f" {arrow} {sign}{pnl_pct:.1f}%"
            else:
                pnl_str = ""
            lines.append(f"• *{ticker}*{qty_str} — {value}{pnl_str}")

        return "\n".join(lines)
