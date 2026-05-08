"""Scheduled gold cache warmer for Phase 3.9 Epic 3."""
from __future__ import annotations

import logging
import time

from sqlalchemy import select

from backend.database import get_session_factory
from backend.market_data.client import get_gold_provider, get_price_cache
from backend.wealth.models.asset import Asset

logger = logging.getLogger(__name__)


def _gold_symbol(extra: dict | None, subtype: str | None = None) -> str:
    value = str((extra or {}).get("type") or (extra or {}).get("symbol") or subtype or "SJC").upper()
    return "RING_24K" if "RING" in value or "NH" in value or "24K" in value else "SJC_GOLD"


async def _held_gold_symbols(db) -> list[str]:
    stmt = select(Asset.extra, Asset.subtype).where(Asset.asset_type == "gold", Asset.is_active.is_(True))
    result = await db.execute(stmt)
    return sorted({_gold_symbol(extra, subtype) for extra, subtype in result.all()})


async def update_all_held_gold() -> dict[str, int]:
    """Fetch held gold symbols and write regular + last-known cache entries."""
    started = time.perf_counter()
    async with get_session_factory()() as db:
        symbols = await _held_gold_symbols(db)
    if not symbols:
        logger.info("Gold updater no-op: symbols_attempted=0 symbols_succeeded=0 duration_ms=0")
        return {"symbols_attempted": 0, "symbols_succeeded": 0, "duration_ms": 0}
    provider = get_gold_provider()
    cache = get_price_cache()
    quotes = await provider.fetch_batch(symbols)
    for quote in quotes:
        await cache.set(quote)
        await cache.set_last_known(quote)
    metrics = {"symbols_attempted": len(symbols), "symbols_succeeded": len(quotes), "duration_ms": int((time.perf_counter() - started) * 1000)}
    logger.info("Gold updater complete: %s", metrics)
    return metrics
