"""``get_market_data`` tool — cache-first real Phase 3.9 market data."""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Type

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent.tools.base import Tool
from backend.agent.tools.schemas import GetMarketDataInput, MarketDataPoint
from backend.market_data.client import get_crypto_quote, get_gold_quote, get_stock_quote
from backend.models.bank_rate import BankRateSnapshot
from backend.models.market_snapshot import MarketSnapshot
from backend.models.news_article import NewsArticle
from backend.models.user import User
from backend.wealth.models.asset import Asset

_PERIOD_TO_FIELD = {
    "1d": "change_1d_pct",
    "7d": "change_1w_pct",
    "30d": "change_1m_pct",
    "90d": None,
    "365d": None,
}

_GOLD_ALIASES = {"GOLD", "SJC", "SJC_GOLD", "VANG", "VÀNG"}
_CRYPTO_ALIASES = {"BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE"}
_BANK_ALIASES = {"VCB": "Vietcombank", "VIETCOMBANK": "Vietcombank"}


class GetMarketDataTool(Tool):
    @property
    def name(self) -> str:
        return "get_market_data"

    @property
    def description(self) -> str:
        return (
            "Get latest real market data for Vietnamese stocks/indexes, "
            "crypto, SJC gold, bank savings rates, and related news. "
            "Returns personal holding context when the user owns the ticker.\n"
            "Examples:\n"
            "- 'VNM giá bao nhiêu?' → ticker='VNM'\n"
            "- 'VN-Index hôm nay' → ticker='VNINDEX'\n"
            "- 'BTC giá bao nhiêu?' → ticker='BTC'\n"
            "- 'vàng SJC?' → ticker='SJC_GOLD'\n"
            "- 'lãi suất Vietcombank?' → ticker='VCB'"
        )

    @property
    def input_schema(self) -> Type:
        return GetMarketDataInput

    @property
    def output_schema(self) -> Type:
        return MarketDataPoint

    async def execute(
        self,
        input_data: GetMarketDataInput,
        user: User,
        db: AsyncSession,
    ) -> MarketDataPoint:
        ticker = input_data.ticker.strip().upper().replace("-", "")
        period = input_data.period or "1d"
        owns, qty, holding = await self._user_holding(db, user.id, ticker)

        if ticker in _GOLD_ALIASES:
            return await self._gold_point(period, owns, qty, holding)

        if ticker in _CRYPTO_ALIASES:
            crypto_point = await self._crypto_point(ticker, period, owns, qty, holding)
            if crypto_point is not None:
                return crypto_point

        if ticker in _BANK_ALIASES:
            bank_point = await self._bank_point(db, ticker, period)
            if bank_point is not None:
                return bank_point

        snapshot = await self._latest_snapshot(db, ticker)
        if snapshot is not None:
            return await self._snapshot_point(db, snapshot, ticker, period, owns, qty, holding)

        return await self._stock_point(ticker, period, owns, qty, holding)

    async def _gold_point(
        self,
        period: str,
        owns: bool,
        qty: float | None,
        holding: Decimal | None,
    ) -> MarketDataPoint:
        try:
            quote = await get_gold_quote("SJC_GOLD")
            return MarketDataPoint(
                ticker="SJC_GOLD",
                asset_name="Vàng SJC",
                current_price=quote.price,
                period=period,
                user_owns=owns,
                user_quantity=qty,
                user_holding_value=holding,
                note="Dữ liệu provider vàng." if not quote.is_stale else "Dữ liệu gần nhất (stale).",
            )
        except Exception as exc:
            return MarketDataPoint(
                ticker="SJC_GOLD",
                current_price=Decimal(0),
                period=period,
                note=f"Chưa lấy được giá vàng SJC: {exc}",
            )

    async def _crypto_point(
        self,
        ticker: str,
        period: str,
        owns: bool,
        qty: float | None,
        holding: Decimal | None,
    ) -> MarketDataPoint | None:
        try:
            quote = await get_crypto_quote(ticker)
        except Exception:
            return None
        return MarketDataPoint(
            ticker=ticker,
            asset_name=ticker,
            current_price=quote.price,
            period=period,
            user_owns=owns,
            user_quantity=qty,
            user_holding_value=holding,
            note="Dữ liệu crypto realtime." if not quote.is_stale else "Dữ liệu gần nhất (stale).",
        )

    async def _bank_point(
        self, db: AsyncSession, ticker: str, period: str
    ) -> MarketDataPoint | None:
        rate = await self._latest_bank_rate(db, "VCB")
        if rate is None:
            return None
        return MarketDataPoint(
            ticker="VCB",
            asset_name=_BANK_ALIASES[ticker],
            current_price=Decimal(rate.rate_pct),
            period=period,
            note=f"Lãi suất tiết kiệm kỳ hạn {rate.tenor_months} tháng (%/năm).",
        )

    async def _snapshot_point(
        self,
        db: AsyncSession,
        snapshot: MarketSnapshot,
        ticker: str,
        period: str,
        owns: bool,
        qty: float | None,
        holding: Decimal | None,
    ) -> MarketDataPoint:
        return MarketDataPoint(
            ticker=ticker,
            asset_name=snapshot.asset_name,
            current_price=Decimal(snapshot.price or 0),
            change_pct=self._change_pct(snapshot, period),
            period=period,
            user_owns=owns,
            user_quantity=qty,
            user_holding_value=holding,
            note=await self._news_note(db, ticker),
        )

    async def _stock_point(
        self,
        ticker: str,
        period: str,
        owns: bool,
        qty: float | None,
        holding: Decimal | None,
    ) -> MarketDataPoint:
        try:
            quote = await get_stock_quote(ticker)
            note = "Dữ liệu cổ phiếu realtime." if not quote.is_stale else "Dữ liệu gần nhất (stale)."
            return MarketDataPoint(
                ticker=ticker,
                asset_name=ticker,
                current_price=quote.price,
                period=period,
                user_owns=owns,
                user_quantity=qty,
                user_holding_value=holding,
                note=note,
            )
        except Exception:
            return MarketDataPoint(
                ticker=ticker,
                current_price=Decimal(0),
                period=period,
                user_owns=owns,
                user_quantity=qty,
                user_holding_value=holding,
                note="Chưa có dữ liệu thị trường cho mã này.",
            )

    @staticmethod
    def _change_pct(snapshot: MarketSnapshot, period: str) -> float | None:
        field = _PERIOD_TO_FIELD.get(period)
        if field is None:
            return None
        raw = getattr(snapshot, field, None)
        return float(raw) if raw is not None else None

    @staticmethod
    async def _latest_snapshot(db: AsyncSession, ticker: str) -> MarketSnapshot | None:
        stmt = (
            select(MarketSnapshot)
            .where(MarketSnapshot.asset_code == ticker)
            .order_by(desc(MarketSnapshot.snapshot_date))
            .limit(1)
        )
        return (await db.execute(stmt)).scalar_one_or_none()

    @staticmethod
    async def _latest_bank_rate(db: AsyncSession, bank_code: str) -> BankRateSnapshot | None:
        stmt = (
            select(BankRateSnapshot)
            .where(BankRateSnapshot.bank_code == bank_code)
            .order_by(desc(BankRateSnapshot.snapshot_date))
            .limit(1)
        )
        return (await db.execute(stmt)).scalar_one_or_none()

    @staticmethod
    async def _news_note(db: AsyncSession, ticker: str) -> str | None:
        stmt = (
            select(NewsArticle.title)
            .where(NewsArticle.related_symbols.any(ticker))
            .order_by(desc(NewsArticle.published_at))
            .limit(1)
        )
        title = (await db.execute(stmt)).scalar_one_or_none()
        return f"Tin mới liên quan: {title}" if title else None

    @staticmethod
    async def _user_holding(
        db: AsyncSession, user_id: uuid.UUID, ticker: str
    ) -> tuple[bool, float | None, Decimal | None]:
        stmt = select(Asset).where(
            Asset.user_id == user_id,
            Asset.is_active.is_(True),
            Asset.extra.is_not(None),
        )
        rows = (await db.execute(stmt)).scalars().all()
        total_qty = 0.0
        total_value = Decimal(0)
        owns = False
        aliases = {ticker, "SJC_GOLD" if ticker in _GOLD_ALIASES else ticker}
        for row in rows:
            extra = row.extra or {}
            sym = str(
                extra.get("ticker") or extra.get("symbol") or extra.get("type") or ""
            ).upper()
            if sym in aliases:
                owns = True
                q = extra.get("quantity") or extra.get("tael")
                try:
                    total_qty += float(q) if q is not None else 0.0
                except (TypeError, ValueError):
                    pass
                total_value += Decimal(row.current_value or 0)
        if not owns:
            return False, None, None
        return True, total_qty if total_qty > 0 else None, total_value
