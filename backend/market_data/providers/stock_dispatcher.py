"""Factory for stock quote dispatcher (SSI primary, VNDIRECT backup)."""
from __future__ import annotations

from backend.market_data.providers.base_dispatcher import Dispatcher, RedisLike
from backend.market_data.providers.stock_ssi import SSIStockProvider
from backend.market_data.providers.stock_vndirect import VNDIRECTStockProvider


def build_stock_dispatcher(redis_client: RedisLike, *, timeout: float = 3.0) -> Dispatcher:
    """Build the Phase 3.9 stock dispatcher with SSI primary and VNDIRECT backup."""
    return Dispatcher(
        SSIStockProvider(timeout=timeout),
        VNDIRECTStockProvider(timeout=timeout),
        redis_client,
        timeout=timeout,
    )
