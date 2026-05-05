"""``get_market_data`` tool — current price + change% for a ticker.

Wraps ``backend.services.market_service`` snapshots and overlays the
user's holding context (quantity, total value) when they own the
ticker. Phase 3B will deepen this with live polling; for Epic 1 we
read from the existing ``market_snapshots`` table only.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Type

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent.tools.base import Tool
from backend.agent.tools.schemas import GetMarketDataInput, MarketDataPoint
from backend.models.market_snapshot import MarketSnapshot
from backend.models.user import User
from backend.wealth.models.asset import Asset

_PERIOD_TO_FIELD = {
    "1d": "change_1d_pct",
    "7d": "change_1w_pct",
    "30d": "change_1m_pct",
    # 90d / 365d not tracked in the snapshot row — return None and a
    # ``note`` telling the user this resolution isn't available yet.
    "90d": None,
    "365d": None,
}


class GetMarketDataTool(Tool):
    @property
    def name(self) -> str:
        return "get_market_data"

    @property
    def description(self) -> str:
        return (
            "Get latest market price + change% for a ticker (Vietnamese "
            "stock, fund, index, or crypto). When the user owns this "
            "ticker, return their quantity and holding value too.\n"
            "\n"
            "Examples:\n"
            "- 'VNM giá bao nhiêu?' → ticker='VNM'\n"
            "- 'VNINDEX hôm nay' → ticker='VNINDEX', period='1d'\n"
            "- 'BTC tuần qua' → ticker='BTC', period='7d'"
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
        ticker = input_data.ticker.strip().upper()
        period = input_data.period or "1d"

        snapshot = await self._latest_snapshot(db, ticker)
        owns, qty, holding = await self._user_holding(db, user.id, ticker)

        if snapshot is None:
            # No data is a real outcome — return a row the formatter
            # can show as "chưa có dữ liệu" rather than raising.
            return MarketDataPoint(
                ticker=ticker,
                asset_name=None,
                current_price=Decimal(0),
                change_pct=None,
                period=period,
                user_owns=owns,
                user_quantity=qty,
                user_holding_value=holding,
                note="Chưa có dữ liệu thị trường cho mã này.",
            )

        change_field = _PERIOD_TO_FIELD.get(period)
        change_pct: float | None
        note: str | None = None
        if change_field is None:
            change_pct = None
            note = f"Chưa lưu {period} change cho mã này — Phase 3B."
        else:
            raw = getattr(snapshot, change_field, None)
            change_pct = float(raw) if raw is not None else None

        return MarketDataPoint(
            ticker=ticker,
            asset_name=snapshot.asset_name,
            current_price=Decimal(snapshot.price or 0),
            change_pct=change_pct,
            period=period,
            user_owns=owns,
            user_quantity=qty,
            user_holding_value=holding,
            note=note,
        )

    # ------------------------------------------------------------------

    @staticmethod
    async def _latest_snapshot(
        db: AsyncSession, ticker: str
    ) -> MarketSnapshot | None:
        stmt = (
            select(MarketSnapshot)
            .where(MarketSnapshot.asset_code == ticker)
            .order_by(desc(MarketSnapshot.snapshot_date))
            .limit(1)
        )
        return (await db.execute(stmt)).scalar_one_or_none()

    @staticmethod
    async def _user_holding(
        db: AsyncSession, user_id: uuid.UUID, ticker: str
    ) -> tuple[bool, float | None, Decimal | None]:
        """Look up whether the user owns ``ticker`` (any asset where
        ``extra.ticker`` or ``extra.symbol`` matches, case-insensitive).
        Aggregates quantity + value across multiple lots."""
        stmt = select(Asset).where(
            Asset.user_id == user_id,
            Asset.is_active.is_(True),
            Asset.extra.is_not(None),
        )
        rows = (await db.execute(stmt)).scalars().all()
        total_qty = 0.0
        total_value = Decimal(0)
        owns = False
        for r in rows:
            extra = r.extra or {}
            sym = (extra.get("ticker") or extra.get("symbol") or "").upper()
            if sym == ticker:
                owns = True
                q = extra.get("quantity")
                try:
                    total_qty += float(q) if q is not None else 0.0
                except (TypeError, ValueError):
                    pass
                total_value += Decimal(r.current_value or 0)
        if not owns:
            return False, None, None
        return True, total_qty if total_qty > 0 else None, total_value
