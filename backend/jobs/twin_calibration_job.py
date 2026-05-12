"""Daily Twin calibration fill (Phase 4.1, Story B.2).

Scans ``twin_calibration_snapshots`` for rows whose horizon has
elapsed, fills ``actual_vnd`` from the user's current stored net
worth, and stamps ``within_band``. The partial index
``idx_twin_calibration_due`` keeps the scan O(due-rows).

Runs once a day at 02:00 ICT — well outside the user-facing morning
briefing window — so backfilling a long horizon never competes with
live traffic. Idempotent: only rows with ``actual_vnd IS NULL`` are
read, so a re-run after a transient DB blip can never double-count.
"""
from __future__ import annotations

import logging

from backend.database import get_session_factory
from backend.services.twin.twin_calibration_service import fill_due_snapshots

logger = logging.getLogger(__name__)


async def run_twin_calibration_job() -> int:
    """Entry point for the APScheduler cron. Returns # snapshots filled."""
    session_factory = get_session_factory()
    async with session_factory() as db:
        try:
            filled = await fill_due_snapshots(db)
            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception("Twin calibration job failed")
            raise
    if filled:
        logger.info("Twin calibration filled %d snapshots", filled)
    return filled
