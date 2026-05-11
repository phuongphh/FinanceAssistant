"""Weekly Financial Twin updater — Sunday 23:00 ICT.

Runs Monte Carlo projections outside user-facing request paths. Per-user
failures are isolated so one bad portfolio cannot stop the whole batch.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from time import perf_counter

from backend import analytics
from backend.database import get_session_factory
from backend.jobs._active_users import get_active_users
from backend.twin.services.twin_projection_service import compute_and_store

logger = logging.getLogger(__name__)

ACTIVE_DAYS = 30
CONCURRENCY_LIMIT = 10


@dataclass(frozen=True, slots=True)
class WeeklyTwinRunMetrics:
    total: int
    succeeded: int
    failed: int
    total_time: float

    def as_dict(self) -> dict[str, int | float]:
        return {
            "total": self.total,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "total_time": round(self.total_time, 3),
        }


async def run_weekly_twin_update(
    *,
    active_days: int = ACTIVE_DAYS,
    concurrency_limit: int = CONCURRENCY_LIMIT,
) -> WeeklyTwinRunMetrics:
    start = perf_counter()
    session_factory = get_session_factory()
    async with session_factory() as db:
        users = await get_active_users(db, days=active_days, require_telegram_id=False)

    semaphore = asyncio.Semaphore(concurrency_limit)

    async def run_one(user) -> bool:
        async with semaphore:
            async with session_factory() as db:
                try:
                    await compute_and_store(db, user.id, scenario="both")
                    await db.commit()
                    return True
                except Exception:
                    await db.rollback()
                    logger.exception("weekly-twin: failed for user=%s", user.id)
                    return False

    results = await asyncio.gather(*(run_one(user) for user in users)) if users else []
    succeeded = sum(1 for ok in results if ok)
    failed = len(results) - succeeded
    metrics = WeeklyTwinRunMetrics(
        total=len(users),
        succeeded=succeeded,
        failed=failed,
        total_time=perf_counter() - start,
    )
    logger.info(
        "weekly-twin: done total=%d succeeded=%d failed=%d total_time=%.3fs",
        metrics.total,
        metrics.succeeded,
        metrics.failed,
        metrics.total_time,
    )
    analytics.track(analytics.EventType.TWIN_WEEKLY_RUN, properties=metrics.as_dict())
    return metrics


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(run_weekly_twin_update())
