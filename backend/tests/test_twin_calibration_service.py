"""Twin calibration service tests (Phase 4.1, Story B.2).

Cover the interpolation math, the within_band fill path, the
display-gate logic, and the layer contract (service flushes, never
commits).
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.models.twin_calibration import TwinCalibrationSnapshot
from backend.services.twin import twin_calibration_service


def _cone():
    return [
        {"year": 0, "p10": 95_000_000, "p50": 100_000_000, "p90": 105_000_000},
        {"year": 1, "p10": 90_000_000, "p50": 110_000_000, "p90": 130_000_000},
        {"year": 5, "p10": 80_000_000, "p50": 200_000_000, "p90": 350_000_000},
    ]


def test_interpolate_horizon_bounds_at_today():
    p10, p50, p90 = twin_calibration_service._interpolate_horizon(
        _cone(), Decimal("100000000"), 0
    )
    assert p50 == Decimal("100000000.00")
    # P10 should be exactly the base when t=0.
    assert p10 == p50 == p90


def test_interpolate_horizon_widens_with_horizon():
    short = twin_calibration_service._interpolate_horizon(
        _cone(), Decimal("100000000"), 7
    )
    long = twin_calibration_service._interpolate_horizon(
        _cone(), Decimal("100000000"), 90
    )
    assert short is not None and long is not None
    # Band width grows monotonically with horizon.
    assert long[2] - long[0] > short[2] - short[0]


def test_interpolate_horizon_returns_none_for_empty_cone():
    assert twin_calibration_service._interpolate_horizon(
        [], Decimal("0"), 30
    ) is None


def test_hit_rate_low_confidence_below_50pct():
    h = twin_calibration_service.HitRate(correct=2, total=5, pct=40)
    assert h.is_low_confidence is True


def test_hit_rate_not_low_confidence_at_or_above_50pct():
    h = twin_calibration_service.HitRate(correct=3, total=5, pct=60)
    assert h.is_low_confidence is False


def test_display_flag_default_on():
    os.environ.pop("TWIN_CALIBRATION_DISPLAY_ENABLED", None)
    assert twin_calibration_service.is_display_enabled() is True


def test_display_flag_off():
    os.environ["TWIN_CALIBRATION_DISPLAY_ENABLED"] = "off"
    try:
        assert twin_calibration_service.is_display_enabled() is False
    finally:
        os.environ.pop("TWIN_CALIBRATION_DISPLAY_ENABLED", None)


@pytest.mark.asyncio
async def test_log_open_snapshot_inserts_three_rows_and_flushes():
    user_id = uuid.uuid4()
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    proj = SimpleNamespace(cone_data=_cone())
    with patch(
        "backend.services.twin.twin_calibration_service.net_worth_calculator.calculate_stored_current",
        new=AsyncMock(return_value=SimpleNamespace(total=Decimal("100000000"))),
    ):
        inserted = await twin_calibration_service.log_open_snapshot(
            db, user_id=user_id, projection=proj
        )

    assert inserted == 3  # one per horizon
    assert db.add.call_count == 3
    db.flush.assert_awaited_once()
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_log_open_snapshot_swallows_exception():
    """Calibration must never block the Twin view — failures are swallowed."""
    user_id = uuid.uuid4()
    db = MagicMock()
    proj = SimpleNamespace(cone_data=_cone())
    with patch(
        "backend.services.twin.twin_calibration_service.net_worth_calculator.calculate_stored_current",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        inserted = await twin_calibration_service.log_open_snapshot(
            db, user_id=user_id, projection=proj
        )
    assert inserted == 0


@pytest.mark.asyncio
async def test_get_hit_rate_returns_none_below_threshold():
    """Below 3 completed snapshots → None so caller hides the section."""
    db = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = [True, True]  # only 2 completed
    result = MagicMock()
    result.scalars.return_value = scalars
    db.execute = AsyncMock(return_value=result)
    assert await twin_calibration_service.get_hit_rate(db, uuid.uuid4()) is None


@pytest.mark.asyncio
async def test_get_hit_rate_computes_pct():
    db = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = [True, True, True, False, True]  # 4/5 = 80%
    result = MagicMock()
    result.scalars.return_value = scalars
    db.execute = AsyncMock(return_value=result)
    hit = await twin_calibration_service.get_hit_rate(db, uuid.uuid4())
    assert hit is not None
    assert hit.correct == 4
    assert hit.total == 5
    assert hit.pct == 80
    assert hit.is_low_confidence is False


@pytest.mark.asyncio
async def test_fill_due_snapshots_marks_within_band():
    """Predicted_at is in the past beyond horizon → snapshot is filled."""
    user_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    snap = TwinCalibrationSnapshot(
        user_id=user_id,
        predicted_at=now - timedelta(days=10),
        horizon_days=7,
        p10_vnd=Decimal("90"),
        p50_vnd=Decimal("100"),
        p90_vnd=Decimal("110"),
    )

    db = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = [snap]
    result = MagicMock()
    result.scalars.return_value = scalars
    db.execute = AsyncMock(return_value=result)
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    with patch(
        "backend.services.twin.twin_calibration_service.net_worth_calculator.calculate_stored_current",
        new=AsyncMock(return_value=SimpleNamespace(total=Decimal("105"))),
    ):
        filled = await twin_calibration_service.fill_due_snapshots(db)

    assert filled == 1
    assert snap.actual_vnd == Decimal("105")
    assert snap.within_band is True
    db.flush.assert_awaited()
    db.commit.assert_not_called()  # caller owns commit


@pytest.mark.asyncio
async def test_fill_due_snapshots_skips_not_yet_due():
    """Predicted_at + horizon still in the future → no fill."""
    user_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    snap = TwinCalibrationSnapshot(
        user_id=user_id,
        predicted_at=now - timedelta(days=2),
        horizon_days=7,  # due in 5 more days
        p10_vnd=Decimal("90"),
        p50_vnd=Decimal("100"),
        p90_vnd=Decimal("110"),
    )

    db = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = [snap]
    result = MagicMock()
    result.scalars.return_value = scalars
    db.execute = AsyncMock(return_value=result)
    db.flush = AsyncMock()

    filled = await twin_calibration_service.fill_due_snapshots(db)
    assert filled == 0
    assert snap.actual_vnd is None
