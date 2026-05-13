"""``get_assets`` tool — the heart of Epic 1.

Wraps ``backend.wealth.services.asset_service`` and adds three
capabilities Phase 3.5 lacked:

1. **Filter** — by type, ticker, value-range, gain-pct.
2. **Sort** — by value, gain (absolute), gain%, name, recency.
3. **Limit** — for "top-N" queries.

The original Phase 3.5 bug ("Mã đang lãi?" returning ALL stocks)
disappears the moment the LLM picks ``filter.gain_pct={gt: 0}``: this
tool then strips losers before the formatter sees them.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Type

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent.tools.base import Tool
from backend.agent.tools.schemas import (
    AssetFilter,
    AssetItem,
    GetAssetsInput,
    GetAssetsOutput,
    NumericFilter,
    SortOrder,
)
from backend.models.user import User
from backend.wealth.models.asset import Asset
from backend.wealth.services import asset_service

# Tickers may live under either key depending on which wizard added
# the asset (see wealth/asset_types.py "ticker"/"symbol"). We check
# both to keep the LLM-facing semantics simple ("ticker").
_TICKER_KEYS = ("ticker", "symbol")


class GetAssetsTool(Tool):
    @property
    def name(self) -> str:
        return "get_assets"

    @property
    def description(self) -> str:
        # Long, example-heavy descriptions are what make function-
        # calling actually work. Each example below was chosen to
        # cover one parameter combination the LLM gets wrong without
        # hand-holding (see Phase 3.7 detailed § "Bẫy thường gặp").
        return (
            "Retrieve the user's assets with optional filtering, sorting, "
            "and limiting. Use this for ANY query about the user's "
            "holdings (assets, stocks, real estate, crypto, gold, cash).\n"
            "\n"
            "Examples (Vietnamese query → tool call):\n"
            "- 'tài sản của tôi' → no filter, no sort\n"
            "- 'mã chứng khoán nào của tôi đang lãi' → "
            "filter={asset_type:'stock', gain_pct:{gt:0}}, sort='gain_pct_desc'\n"
            "- 'top 3 mã lãi nhiều nhất' → "
            "filter={asset_type:'stock'}, sort='gain_pct_desc', limit=3\n"
            "- 'tài sản trên 1 tỷ' → filter={value:{gt:1000000000}}, sort='value_desc'\n"
            "- 'mã đang lỗ' → "
            "filter={asset_type:'stock', gain_pct:{lt:0}}, sort='gain_pct_asc'\n"
            "- 'tôi nắm bao nhiêu VNM' → filter={ticker:['VNM']}\n"
            "- 'tài sản lớn nhất của tôi' → sort='value_desc', limit=1"
        )

    @property
    def input_schema(self) -> Type[BaseModel]:
        return GetAssetsInput

    @property
    def output_schema(self) -> Type[BaseModel]:
        return GetAssetsOutput

    async def execute(
        self,
        input_data: GetAssetsInput,
        user: User,
        db: AsyncSession,
    ) -> GetAssetsOutput:
        # Pre-filter at the DB layer when we have a hard ``asset_type``
        # constraint — saves materialising every asset for users who
        # only want stocks. All other filters happen in Python because
        # they require gain math on Python-side ``Decimal`` arithmetic
        # (snapshots aren't denormalised onto assets).
        type_filter = (
            input_data.filter.asset_type.value
            if input_data.filter and input_data.filter.asset_type
            else None
        )
        all_assets = await asset_service.get_user_assets(
            db, user.id, asset_type=type_filter
        )

        items = [self._to_item(a) for a in all_assets]
        items = list(self._apply_filter(items, input_data.filter))
        items = self._apply_sort(items, input_data.sort)
        if input_data.limit is not None:
            items = items[: input_data.limit]

        total = sum((i.current_value for i in items), start=Decimal(0))
        return GetAssetsOutput(assets=items, total_value=total, count=len(items))

    # ------------------------------------------------------------------
    # filter / sort helpers
    # ------------------------------------------------------------------

    def _apply_filter(
        self, items: list[AssetItem], filt: AssetFilter | None
    ) -> Iterable[AssetItem]:
        if not filt:
            return items

        out: list[AssetItem] = items
        # ``asset_type`` already applied in execute(); applying it
        # again is a no-op so we leave it for defence in depth.
        if filt.asset_type:
            out = [i for i in out if i.asset_type == filt.asset_type.value]

        if filt.ticker:
            wanted = {t.strip().upper() for t in filt.ticker if t}
            out = [i for i in out if i.ticker and i.ticker.upper() in wanted]

        if filt.value:
            out = [
                i
                for i in out
                if _matches_numeric(float(i.current_value), filt.value)
            ]

        if filt.gain_pct:
            # An asset without ``cost_basis`` has no gain_pct; excluding
            # those is the right call — the user asked about winners or
            # losers and an unknown-PnL asset is neither.
            out = [
                i
                for i in out
                if i.gain_pct is not None
                and _matches_numeric(i.gain_pct, filt.gain_pct)
            ]

        return out

    def _apply_sort(
        self, items: list[AssetItem], sort: SortOrder | None
    ) -> list[AssetItem]:
        if sort is None:
            # Default: created_desc (asset_service already returns
            # newest-first, so we leave the order alone).
            return items

        # Sort keys must be tolerant of ``None`` for cost_basis-less
        # assets — push them to the end instead of throwing TypeError.
        def value_key(i: AssetItem) -> Decimal:
            return i.current_value

        def gain_key(i: AssetItem) -> Decimal:
            return i.gain if i.gain is not None else Decimal("-1e30")

        def gain_pct_key(i: AssetItem) -> float:
            return i.gain_pct if i.gain_pct is not None else float("-inf")

        if sort is SortOrder.VALUE_ASC:
            return sorted(items, key=value_key)
        if sort is SortOrder.VALUE_DESC:
            return sorted(items, key=value_key, reverse=True)
        if sort is SortOrder.GAIN_ASC:
            return sorted(items, key=gain_key)
        if sort is SortOrder.GAIN_DESC:
            return sorted(items, key=gain_key, reverse=True)
        if sort is SortOrder.GAIN_PCT_ASC:
            return sorted(items, key=gain_pct_key)
        if sort is SortOrder.GAIN_PCT_DESC:
            return sorted(items, key=gain_pct_key, reverse=True)
        if sort is SortOrder.NAME:
            return sorted(items, key=lambda i: i.name.lower())
        # CREATED_DESC: assets come pre-sorted, no-op.
        return items

    @staticmethod
    def _to_item(asset: Asset) -> AssetItem:
        extra = asset.extra or {}
        ticker: str | None = None
        for key in _TICKER_KEYS:
            v = extra.get(key)
            if v:
                ticker = str(v)
                break

        gain: Decimal | None = None
        gain_pct: float | None = None
        initial = Decimal(asset.initial_value or 0)
        current = Decimal(asset.current_value or 0)
        if initial > 0:
            gain = current - initial
            gain_pct = float(gain / initial * 100)

        quantity = extra.get("quantity")
        try:
            quantity_f = float(quantity) if quantity is not None else None
        except (TypeError, ValueError):
            quantity_f = None

        return AssetItem(
            name=asset.name,
            asset_type=asset.asset_type,
            ticker=ticker,
            quantity=quantity_f,
            current_value=current,
            cost_basis=initial if initial > 0 else None,
            gain=gain,
            gain_pct=gain_pct,
        )


def _matches_numeric(value: float, f: NumericFilter) -> bool:
    """Boolean AND of every populated bound on ``f``.

    Empty filter (all bounds None) returns True — conventional
    interpretation of "no constraint"."""
    if f.gt is not None and not (value > f.gt):
        return False
    if f.gte is not None and not (value >= f.gte):
        return False
    if f.lt is not None and not (value < f.lt):
        return False
    if f.lte is not None and not (value <= f.lte):
        return False
    if f.eq is not None and abs(value - f.eq) >= 0.001:
        return False
    return True
