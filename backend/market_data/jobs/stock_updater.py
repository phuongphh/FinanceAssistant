"""Scheduled stock cache warmer for Phase 3.9."""

from __future__ import annotations

import logging
import time
from datetime import datetime, time as datetime_time, timezone
from decimal import Decimal

from sqlalchemy import desc, select

from backend.database import get_session_factory
from backend.market_data.analytics.alerts import check_movements
from backend.market_data.client import get_price_cache, get_stock_provider
from backend.market_data.normalizer import SNAPSHOT_SOURCE, PriceQuote
from backend.models.market_snapshot import MarketSnapshot
from backend.wealth.models.asset import Asset

logger = logging.getLogger(__name__)

DAILY_MARKET_SYMBOLS = ("VNINDEX",)


async def _held_stock_symbols(db) -> list[str]:
    """Return distinct stock tickers from active assets."""
    stmt = select(Asset.extra).where(
        Asset.asset_type == "stock", Asset.is_active.is_(True)
    )
    result = await db.execute(stmt)
    symbols = {
        str((extra or {}).get("ticker") or (extra or {}).get("symbol") or "")
        .upper()
        .strip()
        for extra in result.scalars().all()
    }
    return sorted(symbol for symbol in symbols if symbol)


async def _latest_snapshot_quotes(db, symbols: list[str]) -> dict[str, PriceQuote]:
    """Load one DB-backed fallback quote per requested symbol.

    Market snapshots outlive Redis and upstream provider incidents.  Converting
    them here closes the gap where valid end-of-day data existed in Postgres but
    the cache warmer could not create either Redis quote key.
    """
    if not symbols:
        return {}
    stmt = (
        select(MarketSnapshot)
        .where(
            MarketSnapshot.asset_code.in_(symbols),
            MarketSnapshot.price.is_not(None),
        )
        .order_by(MarketSnapshot.asset_code, desc(MarketSnapshot.snapshot_date))
    )
    rows = (await db.execute(stmt)).scalars().all()
    quotes: dict[str, PriceQuote] = {}
    for snapshot in rows:
        symbol = snapshot.asset_code.upper()
        if symbol in quotes:
            continue
        extra = snapshot.extra_data or {}
        fetched_at = snapshot.created_at or datetime.combine(
            snapshot.snapshot_date, datetime_time.min, tzinfo=timezone.utc
        )
        quotes[symbol] = PriceQuote(
            symbol=symbol,
            price=Decimal(str(snapshot.price)),
            currency="VND",
            asset_type="stock",
            fetched_at=fetched_at,
            source=SNAPSHOT_SOURCE,
            metadata={
                **extra,
                "change_pct": snapshot.change_1d_pct,
                "snapshot_date": snapshot.snapshot_date.isoformat(),
            },
            is_stale=True,
        )
    return quotes


async def update_all_held_stocks() -> dict[str, int]:
    """Fetch all held stock symbols and write regular + last-known cache entries."""
    started = time.perf_counter()
    async with get_session_factory()() as db:
        held_symbols = await _held_stock_symbols(db)
    symbols = sorted({*DAILY_MARKET_SYMBOLS, *held_symbols})

    provider = get_stock_provider()
    cache = get_price_cache()
    try:
        quotes = await provider.fetch_batch(symbols)
    except Exception as exc:
        logger.warning("Stock providers failed; using market snapshots: %s", exc)
        quotes = []

    # A provider can return a successful but partial batch. Fill only its gaps
    # in one indexed DB query, while always preferring fresher live quotes.
    returned = {quote.symbol for quote in quotes}
    missing = [symbol for symbol in symbols if symbol not in returned]
    snapshot_quotes: dict[str, PriceQuote] = {}
    if missing:
        async with get_session_factory()() as db:
            snapshot_quotes = await _latest_snapshot_quotes(db, missing)

    await check_movements(quotes, cache=cache)
    quotes.extend(snapshot_quotes.values())
    for quote in quotes:
        await cache.set(quote)
        await cache.set_last_known(quote)
    duration_ms = int((time.perf_counter() - started) * 1000)
    metrics = {
        "symbols_attempted": len(symbols),
        "symbols_succeeded": len(quotes),
        "snapshot_fallbacks": len(snapshot_quotes),
        "duration_ms": duration_ms,
    }
    logger.info("Stock updater complete: %s", metrics)
    return metrics
