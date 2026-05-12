"""Backfill twin_calibration_snapshots from historic projections.

Phase 4.1 Story B.2.

Phase 4A dogfood generated weeks of ``twin_projections`` but no
``twin_calibration_snapshots`` rows (the table did not exist yet).
This script replays each historic projection: for every
(user, computed_at) we insert one row per horizon as if the user had
opened their Twin at that time. The daily worker fills the actuals
on the next run.

Usage::

    python -m backend.scripts.twin_calibration_backfill --since 2026-04-01
    python -m backend.scripts.twin_calibration_backfill --dry-run

Idempotent: a (user_id, predicted_at, horizon_days) triple from
``twin_projections.computed_at`` is checked before insert, so re-runs
never duplicate.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from backend.database import get_session_factory
from backend.models.twin_calibration import HORIZONS_DAYS, TwinCalibrationSnapshot
from backend.models.twin_projection import TwinProjection
from backend.services.twin.twin_calibration_service import _interpolate_horizon

logger = logging.getLogger(__name__)


async def _existing_keys(db, user_id, predicted_at) -> set[int]:
    stmt = select(TwinCalibrationSnapshot.horizon_days).where(
        TwinCalibrationSnapshot.user_id == user_id,
        TwinCalibrationSnapshot.predicted_at == predicted_at,
    )
    return set((await db.execute(stmt)).scalars().all())


async def backfill(since: datetime | None, dry_run: bool) -> int:
    factory = get_session_factory()
    inserted_total = 0
    async with factory() as db:
        stmt = select(TwinProjection).order_by(TwinProjection.computed_at.asc())
        if since is not None:
            stmt = stmt.where(TwinProjection.computed_at >= since)
        projections = (await db.execute(stmt)).scalars().all()
        logger.info("Found %d projections to consider", len(projections))

        for proj in projections:
            cone = proj.cone_data or []
            if not cone:
                continue
            # year=0 is "today" relative to the projection; we treat its
            # P50 as the historical net worth baseline. This matches the
            # interpolation contract in twin_calibration_service.
            by_year = {int(p.get("year", -1)): p for p in cone}
            base_point = by_year.get(0) or cone[0]
            base = Decimal(str(base_point.get("p50", 0)))

            existing = await _existing_keys(db, proj.user_id, proj.computed_at)
            for horizon in HORIZONS_DAYS:
                if horizon in existing:
                    continue
                estimate = _interpolate_horizon(cone, base, horizon)
                if estimate is None:
                    continue
                p10, p50, p90 = estimate
                if not dry_run:
                    db.add(
                        TwinCalibrationSnapshot(
                            user_id=proj.user_id,
                            predicted_at=proj.computed_at,
                            horizon_days=horizon,
                            p10_vnd=p10,
                            p50_vnd=p50,
                            p90_vnd=p90,
                        )
                    )
                inserted_total += 1
        if not dry_run:
            await db.commit()
    return inserted_total


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Backfill twin_calibration_snapshots.")
    p.add_argument(
        "--since",
        type=lambda s: datetime.fromisoformat(s).replace(tzinfo=timezone.utc),
        default=None,
        help="ISO date — only backfill projections at or after this date.",
    )
    p.add_argument("--dry-run", action="store_true", help="Count only, do not insert.")
    return p.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = _parse_args()
    n = asyncio.run(backfill(args.since, args.dry_run))
    verb = "Would insert" if args.dry_run else "Inserted"
    print(f"{verb} {n} calibration snapshots")


if __name__ == "__main__":
    main()
