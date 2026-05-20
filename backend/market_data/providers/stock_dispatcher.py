"""Factory for VN stock quote dispatcher.

Order is configurable via ``settings.stock_provider_primary`` so operators
can flip primary/secondary without redeploying when one upstream goes
quiet. Default is VNDIRECT-first because the SSI iboard dchart endpoint
has been unreliable; SSI remains as the warm backup.
"""
from __future__ import annotations

from backend.config import get_settings
from backend.market_data.providers.base_dispatcher import Dispatcher, RedisLike
from backend.market_data.providers.stock_ssi import SSIStockProvider
from backend.market_data.providers.stock_stooq import StooqStockProvider
from backend.market_data.providers.stock_vndirect import VNDIRECTStockProvider


_KNOWN_FOREIGN_TICKERS = {"NVDA", "IBM", "TCEF", "E120"}


class SymbolAwareStockDispatcher:
    """Route likely-foreign tickers to Stooq first for lower latency."""

    def __init__(self, vn_dispatcher: Dispatcher, foreign_provider: StooqStockProvider) -> None:
        self.vn_dispatcher = vn_dispatcher
        self.foreign_provider = foreign_provider

    @property
    def asset_type(self) -> str:
        return "stock"

    async def fetch_quote(self, symbol: str):
        clean = symbol.upper().strip()
        if _is_likely_foreign_symbol(clean):
            try:
                return await self.foreign_provider.fetch_quote(clean)
            except Exception:
                return await self.vn_dispatcher.fetch_quote(clean)
        try:
            return await self.vn_dispatcher.fetch_quote(clean)
        except Exception:
            return await self.foreign_provider.fetch_quote(clean)

    async def fetch_batch(self, symbols: list[str]):
        foreign = [s.upper().strip() for s in symbols if _is_likely_foreign_symbol(s.upper().strip())]
        vn = [s.upper().strip() for s in symbols if s.upper().strip() and s.upper().strip() not in foreign]
        out = []
        if vn:
            try:
                out.extend(await self.vn_dispatcher.fetch_batch(vn))
            except Exception:
                out.extend(await self.foreign_provider.fetch_batch(vn))
        if foreign:
            try:
                out.extend(await self.foreign_provider.fetch_batch(foreign))
            except Exception:
                out.extend(await self.vn_dispatcher.fetch_batch(foreign))
        by_symbol = {q.symbol: q for q in out}
        return [by_symbol[s.upper().strip()] for s in symbols if s.upper().strip() in by_symbol]


def _is_likely_foreign_symbol(symbol: str) -> bool:
    if symbol in _KNOWN_FOREIGN_TICKERS:
        return True
    return len(symbol) > 3 or any(ch.isdigit() for ch in symbol) or "." in symbol or "-" in symbol


def build_stock_dispatcher(redis_client: RedisLike, *, timeout: float = 3.0):
    settings = get_settings()
    ssi = SSIStockProvider(timeout=timeout)
    vnd = VNDIRECTStockProvider(timeout=timeout)
    if (settings.stock_provider_primary or "vndirect").lower() == "ssi":
        primary, secondary = ssi, vnd
    else:
        primary, secondary = vnd, ssi
    vn_dispatcher = Dispatcher(primary, secondary, redis_client, timeout=timeout)
    return SymbolAwareStockDispatcher(vn_dispatcher, StooqStockProvider(timeout=timeout))
