"""Handler for ``query_market`` — show price + personal context."""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.intent.handlers.base import IntentHandler
from backend.intent.intents import IntentResult
from backend.market_data.client import (
    get_fast_crypto_quotes,
    get_gold_quotes,
    get_stock_quote,
)
from backend.market_data.providers.gold_pnj_json import PNJ_GOLD_MENU_PRODUCTS
from backend.market_data.normalizer import PriceQuote
from backend.models.market_snapshot import MarketSnapshot
from backend.models.user import User
from backend.wealth.models.asset import Asset

logger = logging.getLogger(__name__)


class QueryMarketHandler(IntentHandler):
    async def handle(self, intent: IntentResult, user: User, db: AsyncSession) -> str:
        category = str(intent.parameters.get("category") or "").lower()
        if category == "gold":
            return await self._handle_gold_prices()
        if category == "crypto":
            return await self._handle_crypto_prices()

        ticker = intent.parameters.get("ticker")
        if not ticker:
            return "Bạn muốn xem giá mã nào? Ví dụ: VNM, VCB, BTC, VN-Index..."
        ticker = str(ticker).upper()

        live_quote = await self._latest_quote(ticker)
        snapshot = (
            None if live_quote is not None else await self._latest_snapshot(db, ticker)
        )
        if live_quote is None and snapshot is None:
            return (
                f"Mình chưa có dữ liệu cho *{ticker}* 🤔\n"
                "Có thể là mã mình chưa hỗ trợ, hoặc chưa có snapshot hôm nay. "
                "Bạn check lại tên mã giúp nhé."
            )

        price = (
            live_quote.price if live_quote is not None else Decimal(str(snapshot.price))
        )
        change_pct = self._change_pct(live_quote, snapshot)
        lines = [
            f"📊 *{ticker}* hôm nay:",
            f"Giá: {self._format_price(ticker, price)}",
        ]
        if change_pct is not None:
            arrow = "📈" if change_pct >= 0 else "📉"
            sign = "+" if change_pct >= 0 else ""
            lines.append(f"{arrow} {sign}{change_pct:.2f}% so với hôm qua")

        # Personal context: did the user own this ticker?
        owned = await self._user_holding(db, user, ticker)
        if owned is not None:
            qty = (owned.extra or {}).get("quantity")
            if qty:
                value = price * Decimal(str(qty))
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

    async def _latest_quote(self, ticker: str) -> PriceQuote | None:
        """Fetch live market data for on-demand market queries.

        The menu action must not rely only on the daily DB snapshot because
        VN-Index changes intraday after the 08:00 market poller has run.
        """
        try:
            return await get_stock_quote(ticker)
        except Exception as exc:
            logger.warning("Unable to fetch live quote for %s: %s", ticker, exc)
            return None

    @staticmethod
    def _is_index(ticker: str) -> bool:
        return ticker.upper() in {"VNINDEX", "VN30", "HNX", "HNXINDEX", "UPCOM"}

    @classmethod
    def _format_price(cls, ticker: str, price: Decimal) -> str:
        if cls._is_index(ticker):
            return f"{price:,.2f} điểm"
        return f"{price:,.0f}đ"

    @staticmethod
    def _change_pct(
        quote: PriceQuote | None,
        snapshot: MarketSnapshot | None,
    ) -> Decimal | None:
        if quote is not None:
            raw_change = quote.metadata.get("change_pct")
            if raw_change is not None:
                return Decimal(str(raw_change))
        if snapshot is not None and snapshot.change_1d_pct is not None:
            return Decimal(str(snapshot.change_1d_pct))
        return None

    async def _handle_crypto_prices(self) -> str:
        """Show top crypto prices for the menu crypto shortcut.

        ``menu:market:crypto`` sends ``category=crypto`` without a ticker.
        Handle it here so the shortcut shows useful coin prices instead of the
        generic stock-style "which ticker?" clarification.
        """
        symbols = ("BTC", "ETH", "BNB", "SOL", "XRP")
        today_label = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).strftime("%d/%m/%Y")
        lines = [f"₿ *Giá tiền số phổ biến — {today_label}:*"]
        had_quote = False

        try:
            quote_by_symbol = await get_fast_crypto_quotes(list(symbols))
        except Exception as exc:
            logger.warning(
                "Unable to fetch crypto quote batch (%s): %s",
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            quote_by_symbol = {}

        stale_times = []
        for symbol in symbols:
            quote = quote_by_symbol.get(symbol)
            if quote is None:
                lines.append(f"• {symbol}: chưa có dữ liệu")
                continue

            had_quote = True
            if quote.is_stale:
                stale_times.append(quote.fetched_at)
            stale = " (dữ liệu cũ)" if quote.is_stale else ""
            lines.append(f"• {symbol}: {quote.price:,.0f}đ{stale}")

        if stale_times:
            latest = max(stale_times).astimezone().strftime("%H:%M")
            lines.insert(1, f"⚠️ Dữ liệu cập nhật lần cuối: {latest}")

        if not had_quote:
            lines.extend(
                [
                    "",
                    "Mình chưa lấy được giá tiền số lúc này. Bạn thử lại sau nhé.",
                ]
            )
        return "\n".join(lines)

    async def _handle_gold_prices(self) -> str:
        """Show supported gold prices for the menu gold shortcut.

        ``menu:market:gold`` sends ``category=gold`` instead of a stock-like
        ticker. Handle it here so the shortcut does not fall into the generic
        "which ticker?" clarification path.
        """
        symbols = PNJ_GOLD_MENU_PRODUCTS
        lines = ["🥇 *Giá vàng hôm nay:*"]
        had_quote = False

        try:
            quote_by_symbol = await get_gold_quotes([symbol for symbol, _ in symbols])
        except Exception as exc:
            logger.warning(
                "Unable to fetch gold quote batch (%s): %s",
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            quote_by_symbol = {}

        for symbol, label in symbols:
            quote = quote_by_symbol.get(symbol)
            if quote is None:
                lines.append(f"• {label}: chưa có dữ liệu")
                continue

            had_quote = True
            logger.info(
                "Gold quote served for %s: source=%s stale=%s buy=%s sell=%s",
                symbol,
                quote.source,
                quote.is_stale,
                quote.metadata.get("buy_price"),
                quote.metadata.get("sell_price") or quote.price,
            )
            buy_price = quote.metadata.get("buy_price")
            sell_price = quote.metadata.get("sell_price") or quote.price
            stale = " (dữ liệu cũ)" if quote.is_stale else ""
            if buy_price is not None:
                lines.append(
                    f"• {label}: mua {Decimal(str(buy_price)):,.0f}đ · "
                    f"bán {Decimal(str(sell_price)):,.0f}đ/lượng{stale}"
                )
            else:
                lines.append(f"• {label}: {quote.price:,.0f}đ/lượng{stale}")

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
        stmt = select(Asset).where(
            Asset.user_id == user.id,
            Asset.is_active.is_(True),
            Asset.asset_type.in_(["stock", "crypto"]),
        )
        for asset in (await db.execute(stmt)).scalars():
            extra = asset.extra or {}
            symbol = str(extra.get("ticker") or extra.get("symbol") or "").upper()
            if symbol == ticker:
                return asset
        return None
