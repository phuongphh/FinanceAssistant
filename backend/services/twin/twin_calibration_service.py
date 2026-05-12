"""Twin calibration service (Phase 4.1, Story B.2).

Each time the user opens their Twin we log three snapshots — one per
horizon (7/30/90 days). A daily worker later fills ``actual_vnd`` so
the view can render an honest "Bé Tiền đoán đúng X/Y lần" line.

Design notes
------------
- The cone uses **year-indexed** points (year=0 is today, year=1 is
  +1y, …). The shortest horizon stored in the cone is "year=1". To
  derive P10/P50/P90 for 7/30/90-day horizons we **linearly
  interpolate** between year=0 (actual net worth today) and year=1
  (first projected point). This is a pragmatic approximation — the
  alternative (running 1k-path Monte Carlo three more times per Twin
  open) would burn latency on the user-facing path for marginal
  accuracy gains.
- The service ``flush``-es but never ``commit``-s; the caller (handler
  or worker) owns the transaction boundary.
- Display honesty: ``honest_hit_rate`` returns ``None`` when there are
  fewer than 3 completed snapshots so the caller can hide the section
  entirely — better to say nothing than to brag on a sample of 1.
"""
from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.twin_calibration import HORIZONS_DAYS, TwinCalibrationSnapshot
from backend.models.twin_projection import TwinProjection
from backend.wealth.services import net_worth_calculator

logger = logging.getLogger(__name__)

_DISPLAY_FLAG_ENV = "TWIN_CALIBRATION_DISPLAY_ENABLED"
MIN_COMPLETED_FOR_DISPLAY = 3
LOW_CONFIDENCE_THRESHOLD = Decimal("0.5")  # <50% hit-rate triggers honest disclaimer


@dataclass(frozen=True, slots=True)
class HitRate:
    correct: int
    total: int
    pct: int

    @property
    def is_low_confidence(self) -> bool:
        return (
            self.total > 0
            and Decimal(self.correct) / Decimal(self.total) < LOW_CONFIDENCE_THRESHOLD
        )


def is_display_enabled() -> bool:
    """Default ON. Operator can disable display without stopping the
    snapshot pipeline — flipping this flag hides the view section but
    KEEPS logging snapshots so the worker has data when re-enabled.
    """
    return os.environ.get(_DISPLAY_FLAG_ENV, "true").lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _interpolate_horizon(
    cone: list[dict[str, Any]],
    current_net_worth: Decimal,
    horizon_days: int,
) -> tuple[Decimal, Decimal, Decimal] | None:
    """Estimate (P10, P50, P90) at ``horizon_days`` from a year-indexed
    cone by linear interpolation between today (actual) and year=1.

    Returns ``None`` if the cone has no first-year point.
    """
    if not cone:
        return None
    by_year = {int(p.get("year", -1)): p for p in cone}
    first = by_year.get(1) or by_year.get(min(by_year))
    if first is None:
        return None
    t = Decimal(horizon_days) / Decimal(365)
    one_minus_t = Decimal(1) - t
    base = current_net_worth
    p10 = one_minus_t * base + t * Decimal(str(first.get("p10", base)))
    p50 = one_minus_t * base + t * Decimal(str(first.get("p50", base)))
    p90 = one_minus_t * base + t * Decimal(str(first.get("p90", base)))
    return (
        p10.quantize(Decimal("0.01")),
        p50.quantize(Decimal("0.01")),
        p90.quantize(Decimal("0.01")),
    )


async def log_open_snapshot(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    projection: TwinProjection,
) -> int:
    """Insert one row per horizon. Returns count of inserted rows.

    Best-effort: failures are logged but do NOT raise — calibration
    must never block the user from seeing their Twin.
    """
    try:
        nw = await net_worth_calculator.calculate_stored_current(db, user_id)
        current_total = nw.total or Decimal(0)
        now = datetime.now(timezone.utc)
        inserted = 0
        for horizon in HORIZONS_DAYS:
            estimate = _interpolate_horizon(
                projection.cone_data, current_total, horizon
            )
            if estimate is None:
                continue
            p10, p50, p90 = estimate
            db.add(
                TwinCalibrationSnapshot(
                    user_id=user_id,
                    predicted_at=now,
                    horizon_days=horizon,
                    p10_vnd=p10,
                    p50_vnd=p50,
                    p90_vnd=p90,
                )
            )
            inserted += 1
        await db.flush()
        return inserted
    except Exception:
        logger.exception("twin_calibration: log_open_snapshot failed user=%s", user_id)
        return 0


async def get_hit_rate(
    db: AsyncSession, user_id: uuid.UUID
) -> HitRate | None:
    """Return aggregate (correct, total, pct) across ALL horizons.

    Returns ``None`` when fewer than ``MIN_COMPLETED_FOR_DISPLAY``
    snapshots have a recorded actual — caller renders nothing.
    """
    stmt = select(TwinCalibrationSnapshot.within_band).where(
        TwinCalibrationSnapshot.user_id == user_id,
        TwinCalibrationSnapshot.actual_vnd.is_not(None),
    )
    rows = (await db.execute(stmt)).scalars().all()
    total = len(rows)
    if total < MIN_COMPLETED_FOR_DISPLAY:
        return None
    correct = sum(1 for r in rows if r is True)
    pct = int(round(correct * 100 / total)) if total else 0
    return HitRate(correct=correct, total=total, pct=pct)


async def fill_due_snapshots(db: AsyncSession, *, batch_size: int = 500) -> int:
    """Fill ``actual_vnd``/``within_band`` for snapshots whose horizon
    has elapsed. Returns the count filled. Caller owns commit.
    """
    now = datetime.now(timezone.utc)
    stmt = (
        select(TwinCalibrationSnapshot)
        .where(TwinCalibrationSnapshot.actual_vnd.is_(None))
        .order_by(TwinCalibrationSnapshot.predicted_at.asc())
        .limit(batch_size)
    )
    rows = (await db.execute(stmt)).scalars().all()
    filled = 0
    # Per-user cache so we don't recompute net worth N times if a user
    # has multiple due rows.
    nw_cache: dict[uuid.UUID, Decimal] = {}
    for snap in rows:
        predicted_at = snap.predicted_at
        if predicted_at.tzinfo is None:
            predicted_at = predicted_at.replace(tzinfo=timezone.utc)
        due_at = predicted_at + timedelta(days=snap.horizon_days)
        if due_at > now:
            continue
        if snap.user_id not in nw_cache:
            try:
                nw = await net_worth_calculator.calculate_stored_current(
                    db, snap.user_id
                )
            except Exception:
                logger.exception(
                    "twin_calibration: net-worth read failed user=%s", snap.user_id
                )
                continue
            nw_cache[snap.user_id] = nw.total or Decimal(0)
        actual = nw_cache[snap.user_id]
        snap.actual_vnd = actual
        snap.actual_recorded_at = now
        snap.within_band = bool(snap.p10_vnd <= actual <= snap.p90_vnd)
        filled += 1
    if filled:
        await db.flush()
    return filled


__all__ = [
    "HitRate",
    "HORIZONS_DAYS",
    "MIN_COMPLETED_FOR_DISPLAY",
    "fill_due_snapshots",
    "get_hit_rate",
    "is_display_enabled",
    "log_open_snapshot",
]
