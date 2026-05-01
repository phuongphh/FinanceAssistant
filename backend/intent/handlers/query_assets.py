"""Handler for ``query_assets`` — list user's assets, grouped by type."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.formatters.money import format_money_full, format_money_short
from backend.intent.handlers.base import IntentHandler
from backend.intent.intents import IntentResult
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

        return self._format(assets, user, filtered_type=type_filter)

    # -------------------- formatting --------------------

    def _empty_state(self, user: User) -> str:
        name = user.display_name or "bạn"
        return (
            f"💎 {name} chưa thêm tài sản nào cả!\n\n"
            "Mình giúp bạn track tài sản — tiền mặt, chứng khoán, BĐS, vàng...\n"
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
        self, assets, user: User, *, filtered_type: str | None
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
            "━━━━━━━━━━━━━━━━━━━━",
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
            lines.append(f"{icon} *{label}* — {format_money_short(type_total)}")
            for asset in items[:_TOP_N_PER_TYPE]:
                lines.append(
                    f"   • {asset.name}: {format_money_short(asset.current_value)}"
                )
            if len(items) > _TOP_N_PER_TYPE:
                lines.append(
                    f"   _...và {len(items) - _TOP_N_PER_TYPE} mục nữa_"
                )
            lines.append("")

        lines.append("Muốn xem chi tiết phần nào? Hỏi mình nhé 😊")
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
