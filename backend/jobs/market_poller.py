import logging

from backend.database import get_session_factory
from backend.services.market_service import fetch_daily_snapshot, save_snapshots

logger = logging.getLogger(__name__)


async def poll_market():
    """Fetch daily market snapshot and save to DB."""
    async with get_session_factory()() as db:
        try:
            raw_snapshots = await fetch_daily_snapshot()
            if not raw_snapshots:
                logger.warning("No market data fetched")
                return

            saved = await save_snapshots(db, raw_snapshots)
            logger.info("Market poller: saved %d snapshots", len(saved))

            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error("Market poller error: %s", e)
