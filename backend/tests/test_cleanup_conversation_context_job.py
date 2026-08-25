"""Unit tests for the conversation-buffer prune job.

Plain mocks for the DB, same as the service tests — the interesting
behaviour is the cutoff, the batch cap, and the promise that a failing
sweep never raises into the scheduler thread. None of that needs
PostgreSQL.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.jobs import cleanup_conversation_context as job


def _db_returning(ids: list[int]) -> MagicMock:
    scalars = MagicMock()
    scalars.all = MagicMock(return_value=ids)
    result = MagicMock()
    result.scalars = MagicMock(return_value=scalars)

    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    return db


def _factory_for(db) -> MagicMock:
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=db)
    ctx.__aexit__ = AsyncMock(return_value=False)
    factory = MagicMock(return_value=ctx)
    return factory


@pytest.mark.asyncio
class TestPrune:
    async def test_deletes_and_commits_when_rows_are_stale(self):
        db = _db_returning([1, 2, 3])
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)

        deleted = await job._prune(db, cutoff)

        assert deleted == 3
        # One SELECT for the ids, one DELETE for the rows.
        assert db.execute.await_count == 2
        db.commit.assert_awaited_once()

    async def test_no_delete_and_no_commit_when_nothing_is_stale(self):
        db = _db_returning([])
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)

        deleted = await job._prune(db, cutoff)

        assert deleted == 0
        # Only the SELECT ran — an empty sweep must not open a write
        # transaction just to commit nothing.
        assert db.execute.await_count == 1
        db.commit.assert_not_awaited()


@pytest.mark.asyncio
class TestCleanupConversationContext:
    async def test_reports_deleted_rows(self):
        db = _db_returning([1, 2])
        with patch.object(job, "get_session_factory", lambda: _factory_for(db)):
            result = await job.cleanup_conversation_context()
        assert result.deleted_rows == 2
        assert result.batch_capped is False

    async def test_cutoff_is_retention_days_in_the_past(self):
        db = _db_returning([])
        seen: list[datetime] = []

        async def _spy(_db, cutoff):
            seen.append(cutoff)
            return 0

        with patch.object(job, "get_session_factory", lambda: _factory_for(db)), \
                patch.object(job, "_prune", _spy):
            await job.cleanup_conversation_context()

        assert len(seen) == 1
        age = datetime.now(timezone.utc) - seen[0]
        # Days, not the service's 15-minute read TTL — the gap is the
        # debugging window the job docstring argues for.
        assert timedelta(days=job.RETENTION_DAYS - 1) < age
        assert age < timedelta(days=job.RETENTION_DAYS + 1)

    async def test_flags_batch_cap(self):
        db = _db_returning(list(range(job.BATCH_LIMIT)))
        with patch.object(job, "get_session_factory", lambda: _factory_for(db)):
            result = await job.cleanup_conversation_context()
        assert result.deleted_rows == job.BATCH_LIMIT
        assert result.batch_capped is True

    async def test_never_raises_when_the_sweep_blows_up(self):
        def _boom():
            raise RuntimeError("database is on fire")

        with patch.object(job, "get_session_factory", _boom):
            result = await job.cleanup_conversation_context()

        # A dead scheduler thread would take every other job down with
        # it, and nothing user-facing depends on this one.
        assert result.deleted_rows == 0
