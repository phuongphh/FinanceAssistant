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
from backend.market_data.providers.stock_vndirect import VNDIRECTStockProvider


def build_stock_dispatcher(redis_client: RedisLike, *, timeout: float = 3.0) -> Dispatcher:
    settings = get_settings()
    ssi = SSIStockProvider(timeout=timeout)
    vnd = VNDIRECTStockProvider(timeout=timeout)
    if (settings.stock_provider_primary or "vndirect").lower() == "ssi":
        primary, secondary = ssi, vnd
    else:
        primary, secondary = vnd, ssi
    return Dispatcher(primary, secondary, redis_client, timeout=timeout)
