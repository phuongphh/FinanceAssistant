"""Handler for ``query_portfolio`` — investment holdings with current value."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.formatters.money import format_money_full, format_money_short
from backend.intent.handlers.base import IntentHandler
from backend.intent.intents import IntentResult
from backend.intent.wealth_adapt import LevelStyle, decorate, resolve_style
from backend.models.user import User
from backend.wealth.asset_types import get_quantity_unit, get_subtype_label
from backend.wealth.services import asset_service

_DEFAULT_ASSET_TYPE = "stock"
_SUPPORTED_ASSET_TYPES = {"stock", "crypto", "gold"}


class QueryPortfolioHandler(IntentHandler):
    async def handle(
        self, intent: IntentResult, user: User, db: AsyncSession
    ) -> str:
        asset_type = self._asset_type_from(intent)
        assets = await asset_service.get_user_assets(
            db, user.id, asset_type=asset_type
        )
        if not assets:
            return self._empty(user, asset_type)

        style = await resolve_style(db, user)
        formatted = self._format(
            assets, user, asset_type=asset_type, style=style
        )
        return decorate(formatted, style)

    def _asset_type_from(self, intent: IntentResult) -> str:
        raw = str(intent.parameters.get("asset_type") or _DEFAULT_ASSET_TYPE).lower()
        return raw if raw in _SUPPORTED_ASSET_TYPES else _DEFAULT_ASSET_TYPE

    def _empty(self, user: User, asset_type: str) -> str:
        name = user.display_name or "bạn"
        if asset_type == "gold":
            return (
                f"🥇 {name} chưa có tài sản vàng nào trong portfolio.\n\n"
                "Bé Tiền có thể giúp bạn thêm vàng qua /themtaisan nhé."
            )
        if asset_type == "crypto":
            return (
                f"₿ {name} chưa có tiền số nào trong portfolio.\n\n"
                "Thêm crypto đầu tiên qua /themtaisan để mình theo dõi realtime nhé."
            )
        return (
            f"📈 {name} chưa có cổ phiếu / quỹ nào trong portfolio.\n\n"
            "Thêm CK vào portfolio để theo dõi bảng giá riêng của bạn nhé."
        )

    def _format(
        self,
        assets,
        user: User,
        *,
        asset_type: str,
        style: LevelStyle,
    ) -> str:
        # Sort by current value desc — biggest holdings first.
        ordered = sorted(
            assets,
            key=lambda a: Decimal(a.current_value or 0),
            reverse=True,
        )
        total = sum(Decimal(a.current_value or 0) for a in ordered)
        name = user.display_name or "bạn"

        if asset_type == "gold":
            lines = [
                f"🥇 Portfolio vàng của {name}:",
                f"Tổng giá trị: *{format_money_full(total)}*",
                "_Định giá theo SJC realtime khi có dữ liệu thị trường._",
                "",
            ]
            for asset in ordered:
                lines.append(self._format_gold_line(asset, style=style))
            return "\n".join(lines)

        if asset_type == "crypto":
            lines = [
                f"₿ Crypto Portfolio của {name}:",
                f"Tổng giá trị: *{format_money_full(total)}*",
                "",
            ]
            for asset in ordered:
                lines.append(self._format_crypto_line(asset, style=style))
            return "\n".join(lines)

        lines = [
            f"📈 Danh mục đầu tư của {name}:",
            f"Tổng giá trị: *{format_money_full(total)}*",
            "",
        ]
        for asset in ordered:
            lines.append(self._format_stock_line(asset, style=style))

        return "\n".join(lines)

    def _format_stock_line(self, asset, *, style: LevelStyle) -> str:
        ticker = (asset.extra or {}).get("ticker") or asset.name
        quantity = (asset.extra or {}).get("quantity")
        unit = get_quantity_unit(asset.asset_type, asset.subtype)
        qty_str = (
            f" ({quantity:g} {unit})"
            if isinstance(quantity, (int, float))
            else ""
        )
        value = format_money_short(asset.current_value)
        return f"• *{ticker}*{qty_str} — {value}{self._pnl(asset, style=style)}"

    def _format_crypto_line(self, asset, *, style: LevelStyle) -> str:
        extra: dict[str, Any] = asset.extra or {}
        symbol = str(extra.get("symbol") or extra.get("ticker") or asset.name).upper()
        quantity = extra.get("quantity")
        qty_str = (
            f" ({quantity:g} {symbol})"
            if isinstance(quantity, (int, float))
            else ""
        )
        value = format_money_short(asset.current_value)
        return f"• *{symbol}*{qty_str} — {value}{self._pnl(asset, style=style)}"

    def _format_gold_line(self, asset, *, style: LevelStyle) -> str:
        extra: dict[str, Any] = asset.extra or {}
        label = get_subtype_label(asset.subtype) or asset.name or "Vàng"
        quantity = self._gold_quantity(extra)
        qty_str = (
            f" ({_format_quantity(quantity)} lượng)"
            if quantity is not None
            else ""
        )
        stale_marker = (
            " _(giá bạn nhập)_"
            if extra.get("current_price") is not None
            else ""
        )
        return (
            f"• *{label}*{qty_str} — "
            f"{format_money_short(asset.current_value)}"
            f"{self._pnl(asset, style=style)}{stale_marker}"
        )

    def _pnl(self, asset, *, style: LevelStyle) -> str:
        # Hide P&L percentage for Starter — too much information for
        # a user with their first few thousand VND in investments.
        if not style.show_pnl_pct:
            return ""
        pnl_pct = asset.gain_loss_pct
        if pnl_pct is None:
            return ""
        arrow = "🟢" if pnl_pct >= 0 else "🔴"
        sign = "+" if pnl_pct >= 0 else ""
        return f" {arrow} {sign}{pnl_pct:.1f}%"

    def _gold_quantity(self, extra: dict[str, Any]) -> Decimal | None:
        for key in ("quantity", "tael"):
            value = extra.get(key)
            if value is not None:
                return Decimal(str(value))
        grams = extra.get("weight_gram")
        if grams is not None:
            return Decimal(str(grams)) / Decimal("37.5")
        return None


def _format_quantity(quantity: Decimal) -> str:
    text = format(quantity.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text
