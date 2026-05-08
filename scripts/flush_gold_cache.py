"""Flush every Redis key under `market_data:gold:*`.

Use this after wiring a new gold provider into the dispatcher. The price
cache has a 1-hour TTL, so stale quotes from the previous provider chain
will keep being served until expiry — flushing forces the next request
to actually hit the new primary.

Usage on the bot host:

    PYTHONPATH=. python scripts/flush_gold_cache.py
"""
from __future__ import annotations

import asyncio

from backend.market_data.client import get_price_cache


async def main() -> None:
    cache = get_price_cache()
    deleted = await cache.flush_asset_type("gold")
    print(f"Flushed {deleted} key(s) under market_data:gold:*")


if __name__ == "__main__":
    asyncio.run(main())
