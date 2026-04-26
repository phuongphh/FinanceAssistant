"""Tests for the 23:59 daily snapshot job.

Critical paths:

- No active assets → no insert, but still records the analytics row.
- Active assets → batched ON CONFLICT DO NOTHING insert; rowcount
  accurately splits "created" vs "skipped".
- Re-running on the same day → conflict rows are absorbed, not raised.
- Insert exception → the run is marked failed but counters reflect it.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.jobs import daily_snapshot_job as job


def _make_asset(value: Decimal | int = 10_000_000):
    a = MagicMock()
    a.id = uuid.uuid4()
    a.user_id = uuid.uuid4()
    a.current_value = Decimal(value)
    return a


def _patch_factory(execute_result=None, raise_on_execute: Exception | None = None):
    db = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    if raise_on_execute:
        db.execute = AsyncMock(side_effect=raise_on_execute)
    else:
        db.execute = AsyncMock(return_value=execute_result)

    class _Sess:
        async def __aenter__(self): return db
        async def __aexit__(self, *a): pass

    return lambda: _Sess(), db


@pytest.mark.asyncio
async def test_no_active_assets_records_zero_run():
    factory, _ = _patch_factory()
    track_mock = MagicMock()

    with patch(
        "backend.jobs.daily_snapshot_job.get_session_factory",
        return_value=factory,
    ), patch(
        "backend.jobs.daily_snapshot_job._fetch_active_assets",
        new=AsyncMock(return_value=[]),
    ), patch(
        "backend.jobs.daily_snapshot_job.analytics.track",
        track_mock,
    ):
        result = await job.create_daily_snapshots()

    assert result == {"created": 0, "skipped": 0, "failed": 0}
    track_mock.assert_called_once()
    args, kwargs = track_mock.call_args
    assert args[0] == "daily_snapshot_run"
    assert kwargs["properties"]["total"] == 0


@pytest.mark.asyncio
async def test_inserts_batch_and_counts_created():
    """rowcount=3 means all 3 payloads were freshly inserted."""
    assets = [_make_asset(10_000_000) for _ in range(3)]
    insert_result = MagicMock()
    insert_result.rowcount = 3

    factory, _ = _patch_factory(execute_result=insert_result)
    track_mock = MagicMock()

    with patch(
        "backend.jobs.daily_snapshot_job.get_session_factory",
        return_value=factory,
    ), patch(
        "backend.jobs.daily_snapshot_job._fetch_active_assets",
        new=AsyncMock(return_value=assets),
    ), patch(
        "backend.jobs.daily_snapshot_job.analytics.track",
        track_mock,
    ):
        result = await job.create_daily_snapshots(today=date(2026, 4, 26))

    assert result == {"created": 3, "skipped": 0, "failed": 0}
    track_mock.assert_called_once()


@pytest.mark.asyncio
async def test_conflict_rows_count_as_skipped_not_failed():
    """rowcount=1 with 3 payloads = 2 conflicts skipped (idempotent re-run)."""
    assets = [_make_asset() for _ in range(3)]
    insert_result = MagicMock()
    insert_result.rowcount = 1

    factory, _ = _patch_factory(execute_result=insert_result)

    with patch(
        "backend.jobs.daily_snapshot_job.get_session_factory",
        return_value=factory,
    ), patch(
        "backend.jobs.daily_snapshot_job._fetch_active_assets",
        new=AsyncMock(return_value=assets),
    ), patch(
        "backend.jobs.daily_snapshot_job.analytics.track",
        MagicMock(),
    ):
        result = await job.create_daily_snapshots()

    assert result == {"created": 1, "skipped": 2, "failed": 0}


@pytest.mark.asyncio
async def test_insert_exception_marks_run_failed_and_rolls_back():
    assets = [_make_asset() for _ in range(2)]
    factory, db = _patch_factory(raise_on_execute=RuntimeError("db down"))

    with patch(
        "backend.jobs.daily_snapshot_job.get_session_factory",
        return_value=factory,
    ), patch(
        "backend.jobs.daily_snapshot_job._fetch_active_assets",
        new=AsyncMock(return_value=assets),
    ), patch(
        "backend.jobs.daily_snapshot_job.analytics.track",
        MagicMock(),
    ):
        result = await job.create_daily_snapshots()

    assert result["failed"] == 2
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_failure_returns_zero_counters():
    """If we can't even read the asset list, no counters are written."""
    factory, _ = _patch_factory()

    with patch(
        "backend.jobs.daily_snapshot_job.get_session_factory",
        return_value=factory,
    ), patch(
        "backend.jobs.daily_snapshot_job._fetch_active_assets",
        new=AsyncMock(side_effect=RuntimeError("conn refused")),
    ), patch(
        "backend.jobs.daily_snapshot_job.analytics.track",
        MagicMock(),
    ):
        result = await job.create_daily_snapshots()

    assert result == {"created": 0, "skipped": 0, "failed": 0}
