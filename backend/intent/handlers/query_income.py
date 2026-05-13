"""Handler for ``query_income`` — list income streams + monthly total."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.formatters.money import format_money_full, format_money_short
from backend.intent.handlers.base import IntentHandler
from backend.intent.intents import IntentResult
from backend.models.user import User
from backend.intent.handlers.query_cashflow import _strip_legacy_prefix
from backend.wealth.income_types import get_icon, get_label
from backend.wealth.models.income_stream import IncomeStream


class QueryIncomeHandler(IntentHandler):
    async def handle(
        self, intent: IntentResult, user: User, db: AsyncSession
    ) -> str:
        # Phase 3.8 Epic 2: ``amount_monthly`` was renamed to
        # ``amount`` and the schedule lives in ``schedule_type``.
        # Sort by raw ``amount`` so the biggest single payment shows
        # first (matches Phase 3A intent of "headline number on top").
        stmt = (
            select(IncomeStream)
            .where(
                IncomeStream.user_id == user.id,
                IncomeStream.is_active.is_(True),
            )
            .order_by(IncomeStream.amount.desc())
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
                f"💼 Thu nhập của {name} (theo lúc đăng ký):\n"
                f"Lương: *{format_money_full(monthly)}*/tháng\n\n"
                "Muốn thêm nguồn thu nhập (cổ tức, lãi, cho thuê…) "
                "thì gõ /thunhap nhé."
            )
        return (
            f"{name} chưa thêm nguồn thu nhập nào.\n\n"
            "Mình giúp bạn theo dõi thu nhập đa nguồn — gõ /thunhap để bắt đầu."
        )

    def _format(self, streams: list[IncomeStream], user: User) -> str:
        # Phase 3.8 Epic 2: aggregate via ``monthly_equivalent`` so
        # quarterly/annual streams contribute the right share.
        total = sum((s.monthly_equivalent for s in streams), Decimal(0))
        name = user.display_name or "bạn"

        lines = [
            f"💼 Thu nhập hàng tháng của {name}:",
            f"Tổng: *{format_money_full(total)}*/tháng",
            "",
        ]
        for s in streams:
            icon = get_icon(s.stream_type)
            label = get_label(s.stream_type)
            display_name = _strip_legacy_prefix((s.name or "").strip())
            lines.append(
                f"{icon} *{label}* — {display_name}: "
                f"{format_money_short(s.monthly_equivalent)}/tháng"
            )

        return "\n".join(lines)
