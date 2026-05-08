"""Gold provider dispatcher: SJC primary, BTMC JSON-API backup.

PNJ's `/site/gia-vang` page became JS-rendered and SJC's WAF blocks
non-browser TLS fingerprints (HTTP 403). BTMC's public JSON endpoint
is the most durable backup we can scrape without browser automation —
see `gold_btmc.py` for the API contract.
"""
from __future__ import annotations

from backend.market_data.providers.base_dispatcher import Dispatcher
from backend.market_data.providers.gold_btmc import BTMCGoldProvider
from backend.market_data.providers.gold_sjc import SJCGoldProvider


def build_gold_dispatcher(redis_client, *, timeout: float = 5.0) -> Dispatcher:
    return Dispatcher(
        SJCGoldProvider(timeout=timeout),
        BTMCGoldProvider(timeout=timeout),
        redis_client,
        timeout=timeout,
    )
