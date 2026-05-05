"""Handler for ``query_cashflow`` — net cashflow (income − expense) for a period.

Wealth-aware: Starter sees a simple "tiết kiệm được X", Mass Affluent
sees breakdown + savings rate. Income side reads from the IncomeStream
table (Phase 3A) and falls back to ``user.monthly_income`` when no
streams are configured.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.formatters.money import format_money_full, format_money_short
from backend.intent.extractors.time_range import TimeRange
from backend.intent.handlers.base import IntentHandler
from backend.intent.handlers.query_expenses import (
    _resolve_time_range,
    _TIME_LABELS_VI,
    _fetch_expenses,
)
from backend.intent.intents import IntentResult
from backend.intent.wealth_adapt import LevelStyle, decorate, resolve_style
from backend.models.user import User
from backend.wealth.models.income_stream import IncomeStream


class QueryCashflowHandler(IntentHandler):
    async def handle(
        self, intent: IntentResult, user: User, db: AsyncSession
    ) -> str:
        time_range = _resolve_time_range(intent)

        # Income for the period — sum of active streams' monthly amount,
        # prorated by the number of months the period covers. Falls back
        # to the legacy user.monthly_income field when no streams.
        income = await _income_for_period(db, user, time_range)
        expenses = await _fetch_expenses(
            db, user, start=time_range.start, end=time_range.end
        )
        spend = sum(Decimal(tx.amount or 0) for tx in expenses)
        net = income - spend

        style = await resolve_style(db, user)
        text = self._format(
            user, time_range, income=income, spend=spend, net=net, style=style
        )
        return decorate(text, style)

    def _format(
        self,
        user: User,
        time_range: TimeRange,
        *,
        income: Decimal,
        spend: Decimal,
        net: Decimal,
        style: LevelStyle,
    ) -> str:
        name = user.display_name or "bạn"
        label_vi = _TIME_LABELS_VI.get(time_range.label, time_range.label)
        if income <= 0 and spend <= 0:
            return (
                f"{name} chưa có dữ liệu thu / chi {label_vi} 🌱\n"
                "Mình cần ít nhất một nguồn thu và vài giao dịch để tính dòng tiền."
            )

        arrow = "💚" if net >= 0 else "🟥"
        sign = "+" if net >= 0 else "−"
        # Starter: simple. Don't drown them in numbers.
        if style.is_starter:
            if net >= 0:
                return (
                    f"💰 Dòng tiền {label_vi}:\n"
                    f"Bạn dư *{format_money_short(net)}* {label_vi} 💚"
                )
            return (
                f"💰 Dòng tiền {label_vi}:\n"
                f"Tháng này hơi căng — đang vượt thu {format_money_short(abs(net))} 🟥"
            )

        # Young Pro+: breakdown + savings rate when income > 0.
        lines = [
            f"💰 Dòng tiền {label_vi}:",
            f"Thu: *{format_money_full(income)}*",
            f"Chi: *{format_money_full(spend)}*",
            f"{arrow} Dư: *{sign}{format_money_full(abs(net))}*",
        ]
        if style.show_percent_change and income > 0:
            savings_rate = float(net / income * 100)
            lines.append(
                f"_Tỷ lệ tiết kiệm: {savings_rate:+.1f}%_"
            )
        return "\n".join(lines)


async def _income_for_period(
    db: AsyncSession, user: User, time_range: TimeRange
) -> Decimal:
    """Compute income for the period from active streams.

    Streams are stored as a monthly average so we prorate by the number
    of days the period covers vs an average 30-day month. Imperfect, but
    the right ballpark for cashflow questions where users want "thu vs
    chi" not exact accruals.
    """
    stmt = select(IncomeStream).where(
        IncomeStream.user_id == user.id,
        IncomeStream.is_active.is_(True),
    )
    streams = list((await db.execute(stmt)).scalars().all())
    if streams:
        monthly = sum(Decimal(s.amount_monthly or 0) for s in streams)
    elif user.monthly_income:
        monthly = Decimal(user.monthly_income)
    else:
        return Decimal(0)

    days = (time_range.end - time_range.start).days + 1
    return (monthly * Decimal(days) / Decimal(30)).quantize(Decimal("1"))
