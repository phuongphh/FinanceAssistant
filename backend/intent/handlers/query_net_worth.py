"""Handler for ``query_net_worth`` — total + change vs last month.

When the intent carries ``time_range`` (``month_vs_previous`` or ``ytd``)
— set by the asset-list follow-up buttons "📈 So với tháng trước" and
"📈 YTD - Tài sản từ đầu năm đến nay" — we render the shared ``⚖️ So sánh``
comparison block instead of the plain headline, so a tap produces the same
message as typing "So sánh tài sản của tôi so với tháng trước".
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.formatters.comparison import format_comparison_block
from backend.bot.formatters.money import format_money_full, format_money_short
from backend.intent.handlers.base import IntentHandler
from backend.intent.intents import IntentResult
from backend.intent.wealth_adapt import decorate, style_for_level
from backend.models.user import User
from backend.wealth.ladder import detect_level
from backend.wealth.services import net_worth_calculator

# Vietnamese label for the compared metric. Mirrors ``net_worth`` →
# "Tổng tài sản" used across the briefing / asset surfaces (never surface
# the raw English metric key to the user).
_NET_WORTH_LABEL_VI = "Tổng tài sản"


class QueryNetWorthHandler(IntentHandler):
    async def handle(self, intent: IntentResult, user: User, db: AsyncSession) -> str:
        time_range = (intent.parameters or {}).get("time_range")
        if time_range in ("month_vs_previous", "ytd"):
            return await self._handle_comparison(time_range, user, db)

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

        # Anchor the baseline to the end of the previous calendar month so
        # the standalone "so với tháng trước" delta matches the ⚖️ comparison
        # view the asset-list follow-up renders. Using a rolling 30-day
        # window here would drift across month boundaries and produce a
        # different number than the comparison the user sees one tap later.
        change = await net_worth_calculator.calculate_change_vs_last_month_end_from_current(
            db,
            user.id,
            breakdown.total,
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

    async def _handle_comparison(
        self, time_range: str, user: User, db: AsyncSession
    ) -> str:
        """Render the ``⚖️ So sánh Tổng tài sản`` block for the follow-up taps.

        Both branches use the *live* current total (matches the headline the
        user just saw on the asset list) and a snapshot-based baseline:
        - ``month_vs_previous``: baseline = net worth at the end of last month.
        - ``ytd``: baseline = net worth at the start of the year (or the join
          date when the account is younger than the current year).

        Empty/zero state is friendly rather than a divide-by-zero.
        """
        breakdown = await net_worth_calculator.calculate(db, user.id)
        current = breakdown.total
        if current <= 0:
            name = user.display_name or "bạn"
            return (
                f"💎 {name} chưa có tài sản nào trong hệ thống.\n\n"
                "Tap /themtaisan để mình tính tổng tài sản giúp nhé 🚀"
            )

        if time_range == "ytd":
            ytd = await net_worth_calculator.calculate_ytd_return_from_current(
                db,
                user.id,
                current,
                account_created_at=user.created_at,
            )
            previous = ytd.base
            diff = ytd.change_absolute
            # ``change_percentage`` is None when there's no baseline snapshot.
            diff_pct = (
                ytd.change_percentage if ytd.change_percentage is not None else 0.0
            )
            label_b = (
                "Từ ngày tham gia"
                if ytd.is_join_date_fallback
                else f"Đầu năm {date.today().year}"
            )
            label_a = "Hiện tại"
        else:  # month_vs_previous
            change = await net_worth_calculator.calculate_change_vs_last_month_end_from_current(
                db, user.id, current
            )
            previous = change.previous
            diff = change.change_absolute
            diff_pct = change.change_percentage
            label_a = "Tháng này"
            label_b = "Tháng trước"

        return format_comparison_block(
            metric_label=_NET_WORTH_LABEL_VI,
            label_a=label_a,
            value_a=current,
            label_b=label_b,
            value_b=previous,
            diff=diff,
            diff_pct=diff_pct,
        )
