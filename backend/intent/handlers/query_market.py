"""Handler for ``query_market`` — show price + personal context."""
from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.intent.handlers.base import IntentHandler
from backend.intent.intents import IntentResult
from backend.market_data.client import get_gold_quote
from backend.models.market_snapshot import MarketSnapshot
from backend.models.user import User
from backend.wealth.models.asset import Asset

logger = logging.getLogger(__name__)


class QueryMarketHandler(IntentHandler):
    async def handle(
        self, intent: IntentResult, user: User, db: AsyncSession
    ) -> str:
        category = str(intent.parameters.get("category") or "").lower()
        if category == "gold":
            return await self._handle_gold_prices()

        ticker = intent.parameters.get("ticker")
        if not ticker:
            return (
                "Bạn muốn xem giá mã nào? Ví dụ: VNM, VCB, BTC, VN-Index..."
            )
        ticker = str(ticker).upper()

        snapshot = await self._latest_snapshot(db, ticker)
        if snapshot is None:
            return (
                f"Mình chưa có dữ liệu cho *{ticker}* 🤔\n"
                "Có thể là mã mình chưa hỗ trợ, hoặc chưa có snapshot hôm nay. "
                "Bạn check lại tên mã giúp nhé."
            )

        lines = [
            f"📊 *{ticker}* hôm nay:",
            f"Giá: {snapshot.price:,.0f}đ",
        ]
        if snapshot.change_1d_pct is not None:
            arrow = "📈" if snapshot.change_1d_pct >= 0 else "📉"
            sign = "+" if snapshot.change_1d_pct >= 0 else ""
            lines.append(
                f"{arrow} {sign}{snapshot.change_1d_pct:.2f}% so với hôm qua"
            )

        # Personal context: did the user own this ticker?
        owned = await self._user_holding(db, user, ticker)
        if owned is not None:
            qty = (owned.extra or {}).get("quantity")
            if qty:
                value = Decimal(snapshot.price) * Decimal(str(qty))
                lines.extend(
                    [
                        "",
                        f"_Bạn đang sở hữu *{qty:g} {ticker}*_",
                        f"_Giá trị hiện tại: {value:,.0f}đ_",
                    ]
                )
            else:
                lines.extend(
                    [
                        "",
                        f"_Bạn có *{ticker}* trong danh mục "
                        f"(giá trị {owned.current_value:,.0f}đ)_",
                    ]
                )

        return "\n".join(lines)

    async def _handle_gold_prices(self) -> str:
        """Show supported gold prices for the menu gold shortcut.

        ``menu:market:gold`` sends ``category=gold`` instead of a stock-like
        ticker. Handle it here so the shortcut does not fall into the generic
        "which ticker?" clarification path.
        """
        symbols = (("SJC_GOLD", "Vàng SJC"), ("RING_24K", "Vàng nhẫn 24K"))
        lines = ["🥇 *Giá vàng hôm nay:*"]
        had_quote = False

        for symbol, label in symbols:
            try:
                quote = await get_gold_quote(symbol)
            except Exception as exc:
                logger.warning("Unable to fetch gold quote for %s: %s", symbol, exc)
                lines.append(f"• {label}: chưa có dữ liệu")
                continue

            had_quote = True
            buy_price = quote.metadata.get("buy_price")
            sell_price = quote.metadata.get("sell_price") or quote.price
            stale = " (dữ liệu cũ)" if quote.is_stale else ""
            if buy_price is not None:
                lines.append(
                    f"• {label}: mua {Decimal(str(buy_price)):,.0f}đ · "
                    f"bán {Decimal(str(sell_price)):,.0f}đ/lượng{stale}"
                )
            else:
                lines.append(
                    f"• {label}: {quote.price:,.0f}đ/lượng{stale}"
                )

        if not had_quote:
            lines.extend(
                [
                    "",
                    "Mình chưa lấy được giá vàng lúc này. Bạn thử lại sau nhé.",
                ]
            )
        return "\n".join(lines)

    async def _latest_snapshot(
        self, db: AsyncSession, ticker: str
    ) -> MarketSnapshot | None:
        stmt = (
            select(MarketSnapshot)
            .where(MarketSnapshot.asset_code == ticker)
            .order_by(MarketSnapshot.snapshot_date.desc())
            .limit(1)
        )
        return (await db.execute(stmt)).scalar_one_or_none()

    async def _user_holding(
        self, db: AsyncSession, user: User, ticker: str
    ) -> Asset | None:
        # Match either a stock (extra->ticker) or a crypto asset
        # (extra->symbol). One DB roundtrip — query the active assets,
        # filter in Python because the ticker might live in either key.
        stmt = (
            select(Asset)
            .where(
                Asset.user_id == user.id,
                Asset.is_active.is_(True),
                Asset.asset_type.in_(["stock", "crypto"]),
            )
        )
        for asset in (await db.execute(stmt)).scalars():
            extra = asset.extra or {}
            symbol = (
                str(extra.get("ticker") or extra.get("symbol") or "").upper()
            )
            if symbol == ticker:
                return asset
        return None
