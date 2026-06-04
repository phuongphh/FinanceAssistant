"""Handler for ``query_credit_card_debt`` — list outstanding balances per card."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.formatters.money import format_money_full, format_money_short
from backend.intent.handlers.base import IntentHandler
from backend.intent.intents import IntentResult
from backend.models.user import User
from backend.services.credit_card_service import list_credit_cards


class QueryCreditCardDebtHandler(IntentHandler):
    async def handle(
        self, intent: IntentResult, user: User, db: AsyncSession
    ) -> str:
        cards = await list_credit_cards(db, user.id)
        if not cards:
            return self._empty_state(user)
        return self._format(cards, user)

    def _empty_state(self, user: User) -> str:
        name = user.display_name or "bạn"
        return (
            f"💳 {name} chưa có thẻ tín dụng nào trong hệ thống.\n\n"
            "Vào /menu → *Chi tiêu* → *Thẻ tín dụng* để thêm thẻ, "
            "mình sẽ theo dõi dư nợ giúp nhé."
        )

    def _format(self, cards, user: User) -> str:
        total = sum((Decimal(c.debt_balance or 0) for c in cards), Decimal(0))
        name = user.display_name or "bạn"

        lines = [
            f"💳 Dư nợ thẻ tín dụng của {name}:",
            f"Tổng dư nợ: *{format_money_full(total)}*",
            "",
        ]
        for card in cards:
            debt = Decimal(card.debt_balance or 0)
            lines.append(
                f"• *{card.bank_name}*: {format_money_short(debt)}"
            )
        return "\n".join(lines)
