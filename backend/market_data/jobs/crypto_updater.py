"""Scheduled crypto cache warmer for Phase 3.9."""
from __future__ import annotations

import logging
import time

from sqlalchemy import select

from backend.database import get_session_factory
from backend.market_data.client import get_crypto_provider, get_price_cache
from backend.wealth.models.asset import Asset

logger = logging.getLogger(__name__)


async def _held_crypto_symbols(db) -> list[str]:
    """Return distinct crypto symbols from active assets."""
    stmt = select(Asset.extra).where(Asset.asset_type == "crypto", Asset.is_active.is_(True))
    result = await db.execute(stmt)
    symbols = {
        str((extra or {}).get("symbol") or (extra or {}).get("ticker") or "").upper().strip()
        for extra in result.scalars().all()
    }
    return sorted(symbol for symbol in symbols if symbol)


async def update_all_held_crypto() -> dict[str, int]:
    """Fetch all held crypto symbols and write regular + last-known cache entries."""
    started = time.perf_counter()
    async with get_session_factory()() as db:
        symbols = await _held_crypto_symbols(db)
    if not symbols:
        logger.info("Crypto updater no-op: symbols_attempted=0 symbols_succeeded=0 duration_ms=0")
        return {"symbols_attempted": 0, "symbols_succeeded": 0, "duration_ms": 0}

    provider = get_crypto_provider()
    cache = get_price_cache()
    quotes = await provider.fetch_batch(symbols)
    for quote in quotes:
        await cache.set(quote)
        await cache.set_last_known(quote)
    duration_ms = int((time.perf_counter() - started) * 1000)
    metrics = {
        "symbols_attempted": len(symbols),
        "symbols_succeeded": len(quotes),
        "duration_ms": duration_ms,
    }
    logger.info("Crypto updater complete: %s", metrics)
    return metrics
