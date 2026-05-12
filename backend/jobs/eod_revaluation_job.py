"""End-of-day asset revaluation — runs 02:00 Asia/Ho_Chi_Minh.

What this job does
------------------
For every active stock / crypto / gold asset, fetch the latest market
price, rewrite ``asset.current_value``, and **upsert** the previous
day's row in ``asset_snapshots`` so the dashboard's "vs hôm qua /
tuần trước / tháng trước" deltas reflect real market movement instead
of carrying-forward the user-entered cost basis.

Why 02:00
---------
HOSE closes at 15:00 ICT, so by 02:00 the day's close price has been
live for ~11 hours and our cache warmers (``stock_updater``,
``crypto_updater``, ``gold_updater``) have had time to refresh. Running
in the low-activity window also avoids competing with the morning
briefing fan-out at 07:30-08:30.

Why ON CONFLICT DO UPDATE (not DO NOTHING)
------------------------------------------
``create_daily_snapshots`` at 23:59 writes carry-forward rows for
yesterday using DO NOTHING (keeps user-entered values). This job runs
afterwards (02:00 the next day) and explicitly **overrides** those
rows with the market-revalued amounts — that is the whole point of
this job. We target ``snapshot_date = date.today() - 1`` so we are
sealing the books for yesterday.

Idempotency
-----------
Safe to re-run any number of times: each retry recomputes the same
value (or a fresher one if cache warmed between attempts) and upserts
the same (asset_id, snapshot_date) key. The revaluation step uses a
single commit per asset so a partial failure leaves a consistent set
of fully-revalued assets behind.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_session_factory
from backend.wealth.models.asset import Asset
from backend.wealth.models.asset_snapshot import AssetSnapshot
from backend.wealth.valuation.crypto import value_crypto_holding
from backend.wealth.valuation.gold import value_gold_holding
from backend.wealth.valuation.stock import value_stock_holding

logger = logging.getLogger(__name__)

SOURCE_EOD_REVALUATION = "eod_revaluation"

# Asset types that have a live market price worth revaluing against.
# Cash, bank deposits, real estate, etc. keep their user-entered value.
_REVALUABLE_TYPES = {"stock", "crypto", "gold"}


async def _revalue_one(asset: Asset) -> Decimal | None:
    """Compute the fresh market value for one asset; ``None`` if untouched."""
    try:
        if asset.asset_type == "stock":
            valuation = await value_stock_holding(asset)
        elif asset.asset_type == "crypto":
            valuation = await value_crypto_holding(asset)
        elif asset.asset_type == "gold":
            valuation = await value_gold_holding(asset)
        else:
            return None
    except Exception:
        logger.exception(
            "eod-revaluation: valuation failed for asset %s (%s)",
            asset.id,
            asset.asset_type,
        )
        return None

    if valuation.is_stale:
        # The valuation helper reached for ``last-known`` from cache or
        # fell back to user input — neither is "today's market close".
        # Skip the write so we don't replace a hand-entered value with
        # another carry-forward.
        return None
    return Decimal(valuation.current_value)


async def _fetch_revaluable_assets(db: AsyncSession) -> list[Asset]:
    stmt = select(Asset).where(
        Asset.is_active.is_(True),
        Asset.asset_type.in_(sorted(_REVALUABLE_TYPES)),
    )
    return list((await db.execute(stmt)).scalars())


async def revalue_and_snapshot(
    *,
    today: date | None = None,
) -> dict[str, int]:
    """Revalue every market-priced asset and seal yesterday's snapshot.

    Returns counters ``{"revalued", "skipped", "snapshotted", "failed"}``
    for analytics + scheduler logs.
    """
    today = today or date.today()
    yesterday = today - timedelta(days=1)

    revalued = skipped = failed = 0
    snapshot_payloads: list[dict] = []

    session_factory = get_session_factory()
    async with session_factory() as db:
        try:
            assets = await _fetch_revaluable_assets(db)
        except Exception:
            logger.exception("eod-revaluation: failed to load assets")
            return {"revalued": 0, "skipped": 0, "snapshotted": 0, "failed": 0}

        for asset in assets:
            new_value = await _revalue_one(asset)
            if new_value is None:
                skipped += 1
                # Still snapshot using the existing stored value so the
                # day has a closing row — but only if no row exists yet
                # (the upsert below covers that).
                snapshot_payloads.append({
                    "asset_id": asset.id,
                    "user_id": asset.user_id,
                    "snapshot_date": yesterday,
                    "value": Decimal(asset.current_value or 0),
                    "source": SOURCE_EOD_REVALUATION,
                })
                continue

            asset.current_value = new_value
            revalued += 1
            snapshot_payloads.append({
                "asset_id": asset.id,
                "user_id": asset.user_id,
                "snapshot_date": yesterday,
                "value": new_value,
                "source": SOURCE_EOD_REVALUATION,
            })

        try:
            await db.commit()
        except Exception:
            logger.exception("eod-revaluation: commit of asset values failed")
            await db.rollback()
            return {"revalued": 0, "skipped": skipped, "snapshotted": 0, "failed": revalued}

    snapshotted = 0
    if snapshot_payloads:
        async with session_factory() as db:
            try:
                stmt = pg_insert(AssetSnapshot).values(snapshot_payloads)
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_asset_snapshot_date",
                    set_={
                        "value": stmt.excluded.value,
                        "source": stmt.excluded.source,
                    },
                )
                result = await db.execute(stmt)
                await db.commit()
                snapshotted = int(result.rowcount or len(snapshot_payloads))
            except Exception:
                logger.exception(
                    "eod-revaluation: snapshot upsert failed (count=%d)",
                    len(snapshot_payloads),
                )
                await db.rollback()
                failed += len(snapshot_payloads)

    # Bust the VNIndex screen cache so the next user tap renders a
    # fresh briefing if the snapshot store changed underneath.
    try:
        from backend.bot.handlers.menu_handler import VNINDEX_SCREEN_CACHE_KEY
        from backend.market_data.client import get_redis_client

        await get_redis_client().delete(VNINDEX_SCREEN_CACHE_KEY)
    except Exception:
        logger.debug("eod-revaluation: could not bust VNIndex cache", exc_info=True)

    logger.info(
        "eod-revaluation: done — revalued=%d skipped=%d snapshotted=%d failed=%d",
        revalued, skipped, snapshotted, failed,
    )
    return {
        "revalued": revalued,
        "skipped": skipped,
        "snapshotted": snapshotted,
        "failed": failed,
    }


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(revalue_and_snapshot())
