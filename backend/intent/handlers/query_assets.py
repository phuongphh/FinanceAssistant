"""Handler for ``query_assets`` — list user's assets, grouped by type."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.formatters.money import format_money_full, format_money_short
from backend.intent.handlers.base import IntentHandler
from backend.intent.intents import IntentResult
from backend.intent.wealth_adapt import LevelStyle, decorate, resolve_style
from backend.models.user import User
from backend.wealth.services import asset_service

# Top-N items per asset type to render before the "...và X mục nữa" tail.
_TOP_N_PER_TYPE = 3


class QueryAssetsHandler(IntentHandler):
    async def handle(
        self, intent: IntentResult, user: User, db: AsyncSession
    ) -> str:
        type_filter = intent.parameters.get("asset_type")
        assets = await asset_service.get_user_assets(
            db, user.id, asset_type=type_filter if type_filter else None
        )

        if not assets:
            if type_filter:
                return self._no_match_for_type(type_filter, user)
            return self._empty_state(user)

        style = await resolve_style(db, user)
        formatted = self._format(
            assets, user, filtered_type=type_filter, style=style
        )
        return decorate(formatted, style)

    # -------------------- formatting --------------------

    def _empty_state(self, user: User) -> str:
        name = user.display_name or "bạn"
        return (
            f"💎 {name} chưa thêm tài sản nào cả!\n\n"
            "Mình giúp bạn theo dõi tài sản — tiền mặt, chứng khoán, BĐS, vàng…\n"
            "Tap vào /themtaisan để bắt đầu nhé 🚀"
        )

    def _no_match_for_type(self, asset_type: str, user: User) -> str:
        label = _ASSET_LABELS.get(asset_type, asset_type)
        name = user.display_name or "bạn"
        return (
            f"{name} chưa có {label} nào cả 🤔\n\n"
            "Mình có thể giúp bạn thêm vào không? Tap /themtaisan"
        )

    def _format(
        self,
        assets,
        user: User,
        *,
        filtered_type: str | None,
        style: LevelStyle,
    ) -> str:
        by_type: dict[str, list] = {}
        total = Decimal(0)
        for asset in assets:
            value = Decimal(asset.current_value or 0)
            total += value
            by_type.setdefault(asset.asset_type, []).append(asset)

        name = user.display_name or "bạn"
        if filtered_type:
            label = _ASSET_LABELS.get(filtered_type, filtered_type)
            header = f"💎 {label} của {name}:"
        else:
            header = f"💎 Tài sản hiện tại của {name}:"

        lines = [
            header,
            f"Tổng: *{format_money_full(total)}*",
            "",
        ]

        # Sort buckets by total value descending so the user sees their
        # biggest holdings first.
        ordered = sorted(
            by_type.items(),
            key=lambda kv: sum(Decimal(a.current_value or 0) for a in kv[1]),
            reverse=True,
        )
        for asset_type, items in ordered:
            icon = _ASSET_ICONS.get(asset_type, "📌")
            label = _ASSET_LABELS.get(asset_type, asset_type)
            type_total = sum(Decimal(a.current_value or 0) for a in items)
            # Show allocation % only for Mass Affluent + HNW. Starter and
            # Young Pro see the raw amount only — fewer numbers to scan.
            type_line = f"{icon} *{label}* — {format_money_short(type_total)}"
            if style.show_allocation_pct and total > 0:
                pct = float(type_total / total * 100)
                type_line += f" _({pct:.0f}%)_"
            lines.append(type_line)
            for asset in items[:_TOP_N_PER_TYPE]:
                lines.append(
                    f"   • {asset.name}: {format_money_short(asset.current_value)}"
                )
            if len(items) > _TOP_N_PER_TYPE:
                lines.append(
                    f"   _...và {len(items) - _TOP_N_PER_TYPE} mục nữa_"
                )
            lines.append("")

        # The personality wrapper adds its own follow-up prompt — only
        # add the static one for Starter (where the wrapper is muted to
        # avoid stacking too many "ơi" greetings on top of "Bước đầu
        # tốt!" lines).
        if style.is_starter:
            lines.append("Hỏi mình nếu cần thêm chi tiết nhé 😊")
        return "\n".join(lines).rstrip()


# Inline tables — kept here rather than re-loading asset_categories.yaml
# for every reply. If the YAML changes we update both; the reverse risk
# (yaml drift) is caught by Phase 3A's keyboard test.
_ASSET_LABELS = {
    "cash": "Tiền mặt & Tài khoản",
    "stock": "Chứng khoán",
    "real_estate": "Bất động sản",
    "crypto": "Tiền số",
    "gold": "Vàng",
    "other": "Khác",
}

_ASSET_ICONS = {
    "cash": "💵",
    "stock": "📈",
    "real_estate": "🏠",
    "crypto": "₿",
    "gold": "🥇",
    "other": "📦",
}
