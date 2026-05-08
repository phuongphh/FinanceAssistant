"""Gold provider dispatcher: SJC primary, PNJ backup."""
from __future__ import annotations

from backend.market_data.providers.base_dispatcher import Dispatcher
from backend.market_data.providers.gold_pnj import PNJGoldProvider
from backend.market_data.providers.gold_sjc import SJCGoldProvider


def build_gold_dispatcher(redis_client, *, timeout: float = 5.0) -> Dispatcher:
    return Dispatcher(SJCGoldProvider(timeout=timeout), PNJGoldProvider(timeout=timeout), redis_client, timeout=timeout)
