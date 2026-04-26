"""Daily asset snapshot job — runs 23:59 Asia/Ho_Chi_Minh.

Captures end-of-day ``current_value`` for every active asset so the
morning briefing's "vs hôm qua / tuần trước / tháng trước" comparisons
have data points to anchor on.

Idempotency
-----------
The unique constraint ``uq_asset_snapshot_date`` (asset_id +
snapshot_date) makes the job safe to re-run. We use Postgres
``INSERT ... ON CONFLICT DO NOTHING`` so:

- If the user already updated an asset's value today (via the
  wizard or ``PUT /assets/{id}/value``), the existing snapshot
  is kept untouched — their input wins over our auto-snapshot.
- If the job runs twice in the same day (e.g. retry after a
  scheduler hiccup), no duplicates and no exceptions.

Reference: docs/current/phase-3a-detailed.md § 2.4
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend import analytics
from backend.database import get_session_factory
from backend.wealth.models.asset import Asset
from backend.wealth.models.asset_snapshot import AssetSnapshot

logger = logging.getLogger(__name__)

# Marks the snapshot as written by this scheduler rather than user
# input — used by Phase 4 reporting to gate "real" valuations vs
# carried-forward ones.
SOURCE_AUTO_DAILY = "auto_daily"


async def _fetch_active_assets(db: AsyncSession) -> list[Asset]:
    stmt = select(Asset).where(Asset.is_active.is_(True))
    return list((await db.execute(stmt)).scalars())


async def create_daily_snapshots(
    *,
    today: date | None = None,
) -> dict[str, int]:
    """Snapshot every active asset; return run counters.

    ``today`` is injectable for tests; production calls leave it as
    ``None`` and we resolve to ``date.today()`` (process timezone).

    Returns ``{"created", "skipped", "failed"}``. Total active assets
    = sum of the three; exposed so the analytics row carries the
    actual delta even when the unique constraint absorbed everything.
    """
    today = today or date.today()
    created = skipped = failed = 0

    session_factory = get_session_factory()

    async with session_factory() as db:
        try:
            assets = await _fetch_active_assets(db)
        except Exception:
            logger.exception("daily-snapshot: failed to load active assets")
            return {"created": 0, "skipped": 0, "failed": 0}

    if not assets:
        logger.info("daily-snapshot: no active assets — nothing to do")
        analytics.track(
            analytics.EventType.DAILY_SNAPSHOT_RUN,
            properties={
                "created": 0, "skipped": 0, "failed": 0, "total": 0,
            },
        )
        return {"created": 0, "skipped": 0, "failed": 0}

    # Build a single batch payload. ``ON CONFLICT DO NOTHING`` does the
    # "skip if today's row exists" check at the DB level — much faster
    # than checking each asset individually as the spec doc draft did.
    payloads: list[dict] = []
    for asset in assets:
        try:
            payloads.append({
                "asset_id": asset.id,
                "user_id": asset.user_id,
                "snapshot_date": today,
                "value": asset.current_value,
                "source": SOURCE_AUTO_DAILY,
            })
        except Exception:
            failed += 1
            logger.exception(
                "daily-snapshot: payload build failed for asset %s",
                getattr(asset, "id", "<?>"),
            )

    if payloads:
        async with session_factory() as db:
            try:
                stmt = pg_insert(AssetSnapshot).values(payloads)
                stmt = stmt.on_conflict_do_nothing(
                    constraint="uq_asset_snapshot_date",
                )
                # ``execute().rowcount`` reflects rows actually
                # inserted — ON CONFLICT DO NOTHING returns 0 for the
                # conflicted rows, so this gives us the "created" count
                # cleanly without a follow-up query.
                result = await db.execute(stmt)
                await db.commit()
                created = int(result.rowcount or 0)
                skipped = len(payloads) - created
            except Exception:
                failed += len(payloads)
                logger.exception(
                    "daily-snapshot: batch insert failed (count=%d)",
                    len(payloads),
                )
                await db.rollback()

    logger.info(
        "daily-snapshot: done — created=%d skipped=%d failed=%d total=%d",
        created, skipped, failed, len(assets),
    )

    analytics.track(
        analytics.EventType.DAILY_SNAPSHOT_RUN,
        properties={
            "created": created,
            "skipped": skipped,
            "failed": failed,
            "total": len(assets),
        },
    )

    return {"created": created, "skipped": skipped, "failed": failed}


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(create_daily_snapshots())
