"""Seed beginning-of-year prices for YTD analytics."""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

from sqlalchemy.dialects.postgresql import insert

from backend.database import get_session_factory
from backend.market_data.jobs.stock_updater import _held_stock_symbols
from backend.market_data.client import get_stock_provider
from backend.models.stock_historical_price import StockHistoricalPrice

logger = logging.getLogger(__name__)


async def seed_year_start_stock_prices() -> dict[str, int]:
    """Persist Jan-1-equivalent current prices once a year as YTD baseline."""
    price_date = date(date.today().year, 1, 1)
    async with get_session_factory()() as db:
        symbols = await _held_stock_symbols(db)
    if not symbols:
        return {"symbols_attempted": 0, "symbols_seeded": 0}
    quotes = await get_stock_provider().fetch_batch(symbols)
    async with get_session_factory()() as db:
        seeded = 0
        for quote in quotes:
            stmt = insert(StockHistoricalPrice).values(
                symbol=quote.symbol,
                price_date=price_date,
                close_price=quote.price,
                source=quote.source,
            ).on_conflict_do_nothing(index_elements=["symbol", "price_date"])
            result = await db.execute(stmt)
            seeded += int(result.rowcount or 0)
        await db.commit()
    metrics = {"symbols_attempted": len(symbols), "symbols_seeded": seeded}
    logger.info("Historical price seeder complete: %s", metrics)
    return metrics
