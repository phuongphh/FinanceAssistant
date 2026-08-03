"""Phase 5.1 #1.4 — the two-pass media sweep.

The DoD lines under test: *"job xoá row hết hạn + file tương ứng; chạy
hai lần liên tiếp không đổi gì; orphan sweep dọn file của một publish đã
rollback; đếm row-driven và orphan riêng."*

Two invariants carry the design and both are asserted rather than
described:

* **Rows are committed before files are deleted.** The reverse ordering
  turns a failed commit into live rows pointing at nothing — a broken
  image for anyone still holding the URL. The current ordering fails the
  other way, and pass 2 self-heals that.
* **Pass 2 only deletes what no row claims, and only after the grace
  period.** A file written seconds ago may belong to a transaction that
  has not committed yet; deleting it would break a request in flight.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from tests.test_phase_5_1.conftest import FakeMediaSession, InMemoryStorage

from backend.jobs import cleanup_media as job
from backend.models.media_object import MediaObject


def _row(*, expires_in: timedelta, storage_key: str | None = None):
    row = MediaObject(
        user_id=uuid4(),
        token_hash="0" * 64,
        content_type="image/png",
        byte_size=3,
        storage_key=storage_key or uuid4().hex,
        expires_at=datetime.now(timezone.utc) + expires_in,
    )
    row.id = uuid4()
    row.deleted_at = None
    return row


async def _seed(storage: InMemoryStorage, *rows):
    for row in rows:
        await storage.write(row.storage_key, b"png")


# ---------------------------------------------------------------------
# Pass 1 — row-driven
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expired_rows_are_soft_deleted_and_their_files_removed():
    expired = _row(expires_in=timedelta(minutes=-1))
    live = _row(expires_in=timedelta(minutes=10))
    db, storage = FakeMediaSession([expired, live]), InMemoryStorage()
    await _seed(storage, expired, live)

    rows, files = await job._sweep_expired(db, storage)

    assert (rows, files) == (1, 1)
    assert expired.deleted_at is not None
    assert live.deleted_at is None
    assert expired.storage_key not in storage.objects
    assert live.storage_key in storage.objects


@pytest.mark.asyncio
async def test_rows_are_never_hard_deleted():
    """Soft delete, per the project-wide rule — the row stays as the
    record that a URL existed and when it stopped working."""
    expired = _row(expires_in=timedelta(minutes=-1))
    db, storage = FakeMediaSession([expired]), InMemoryStorage()
    await _seed(storage, expired)

    await job._sweep_expired(db, storage)

    assert db.rows == [expired]


@pytest.mark.asyncio
async def test_rows_are_committed_before_files_are_deleted():
    """The ordering invariant, asserted from the storage side.

    A storage that records the commit count at delete time proves the
    commit already happened — a docstring cannot.
    """
    expired = _row(expires_in=timedelta(minutes=-1))
    db = FakeMediaSession([expired])

    class OrderRecordingStorage(InMemoryStorage):
        def __init__(self) -> None:
            super().__init__()
            self.commits_at_delete: list[int] = []

        async def delete(self, key: str) -> bool:
            self.commits_at_delete.append(db.commits)
            return await super().delete(key)

    storage = OrderRecordingStorage()
    await _seed(storage, expired)

    await job._sweep_expired(db, storage)

    assert storage.commits_at_delete == [1]


@pytest.mark.asyncio
async def test_a_missing_file_does_not_stop_the_sweep():
    """A row whose file is already gone still gets swept; it just isn't
    counted as a file deletion."""
    a = _row(expires_in=timedelta(minutes=-1))
    b = _row(expires_in=timedelta(minutes=-1))
    db, storage = FakeMediaSession([a, b]), InMemoryStorage()
    await _seed(storage, b)  # a's file was already removed

    rows, files = await job._sweep_expired(db, storage)

    assert (rows, files) == (2, 1)
    assert a.deleted_at is not None and b.deleted_at is not None


@pytest.mark.asyncio
async def test_already_swept_rows_are_not_revisited():
    swept = _row(expires_in=timedelta(minutes=-1))
    swept.deleted_at = datetime.now(timezone.utc)
    db, storage = FakeMediaSession([swept]), InMemoryStorage()

    assert await job._sweep_expired(db, storage) == (0, 0)
    assert db.commits == 0  # nothing to do, no transaction opened


@pytest.mark.asyncio
async def test_sweep_is_idempotent():
    expired = _row(expires_in=timedelta(minutes=-1))
    db, storage = FakeMediaSession([expired]), InMemoryStorage()
    await _seed(storage, expired)

    first = await job._sweep_expired(db, storage)
    second = await job._sweep_expired(db, storage)

    assert first == (1, 1)
    assert second == (0, 0)


@pytest.mark.asyncio
async def test_sweep_is_capped_per_run():
    """One pathological backlog must not hold a transaction open for
    minutes; the next hourly run takes the remainder."""
    rows = [_row(expires_in=timedelta(minutes=-1)) for _ in range(3)]
    db, storage = FakeMediaSession(rows), InMemoryStorage()
    await _seed(storage, *rows)

    original = job.BATCH_LIMIT
    job.BATCH_LIMIT = 2
    try:
        assert await job._sweep_expired(db, storage) == (2, 2)
        assert await job._sweep_expired(db, storage) == (1, 1)
    finally:
        job.BATCH_LIMIT = original


# ---------------------------------------------------------------------
# Pass 2 — the orphan sweep
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orphan_sweep_removes_a_rolled_back_publishs_file():
    """The case pass 1 structurally cannot see.

    ``publish`` wrote the bytes, the caller's transaction rolled back, so
    no row will ever point at the file.
    """
    db, storage = FakeMediaSession(), InMemoryStorage()
    orphan = uuid4().hex
    await storage.write(orphan, b"png")
    storage.age(orphan, datetime.now(timezone.utc) - timedelta(hours=2))

    assert await job._sweep_orphans(db, storage, grace_seconds=3600) == 1
    assert storage.objects == {}


@pytest.mark.asyncio
async def test_orphan_sweep_respects_the_grace_period():
    """A file written seconds ago may belong to a transaction that has
    not committed yet."""
    db, storage = FakeMediaSession(), InMemoryStorage()
    fresh = uuid4().hex
    await storage.write(fresh, b"png")

    assert await job._sweep_orphans(db, storage, grace_seconds=3600) == 0
    assert fresh in storage.objects


@pytest.mark.asyncio
async def test_orphan_sweep_leaves_files_a_row_claims():
    """Including soft-deleted rows: pass 1 owns those files, and a
    delete here would double-count them."""
    live = _row(expires_in=timedelta(minutes=10))
    swept = _row(expires_in=timedelta(minutes=-30))
    swept.deleted_at = datetime.now(timezone.utc)
    db, storage = FakeMediaSession([live, swept]), InMemoryStorage()
    await _seed(storage, live, swept)
    old = datetime.now(timezone.utc) - timedelta(hours=2)
    storage.age(live.storage_key, old)
    storage.age(swept.storage_key, old)

    assert await job._sweep_orphans(db, storage, grace_seconds=3600) == 0
    assert len(storage.objects) == 2


@pytest.mark.asyncio
async def test_orphan_sweep_on_empty_storage_asks_the_database_nothing():
    """No files means no query — the fake raises on any statement it
    does not recognise, so an unexpected round trip fails here."""
    db, storage = FakeMediaSession(), InMemoryStorage()

    assert await job._sweep_orphans(db, storage, grace_seconds=3600) == 0


@pytest.mark.asyncio
async def test_orphan_sweep_is_idempotent():
    db, storage = FakeMediaSession(), InMemoryStorage()
    orphan = uuid4().hex
    await storage.write(orphan, b"png")
    storage.age(orphan, datetime.now(timezone.utc) - timedelta(hours=2))

    assert await job._sweep_orphans(db, storage, grace_seconds=3600) == 1
    assert await job._sweep_orphans(db, storage, grace_seconds=3600) == 0


# ---------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------


class _FakeSessionFactory:
    def __init__(self, db) -> None:
        self._db = db

    def __call__(self):
        return self

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, *exc) -> bool:
        return False


def _wire(monkeypatch, db, storage, *, grace_seconds=3600):
    class _Settings:
        media_storage_path = "/unused"
        media_orphan_grace_seconds = grace_seconds

    monkeypatch.setattr(job, "get_settings", lambda: _Settings())
    monkeypatch.setattr(job, "FilesystemMediaStorage", lambda path: storage)
    monkeypatch.setattr(
        job, "get_session_factory", lambda: _FakeSessionFactory(db)
    )


@pytest.mark.asyncio
async def test_cleanup_media_counts_the_two_passes_separately(monkeypatch):
    """Summing them would hide the signal.

    ``expired_rows`` rising with traffic is healthy; ``orphan_files``
    above zero means transactions are rolling back after publish, which
    is a statement about upstream code, not about media.
    """
    expired = _row(expires_in=timedelta(minutes=-1))
    db, storage = FakeMediaSession([expired]), InMemoryStorage()
    await _seed(storage, expired)
    orphan = uuid4().hex
    await storage.write(orphan, b"png")
    storage.age(orphan, datetime.now(timezone.utc) - timedelta(hours=2))
    _wire(monkeypatch, db, storage)

    result = await job.cleanup_media()

    assert result.expired_rows == 1
    assert result.expired_files_deleted == 1
    assert result.orphan_files_deleted == 1
    assert storage.objects == {}


@pytest.mark.asyncio
async def test_cleanup_media_swallows_a_failing_sweep(monkeypatch):
    """One bad run must not kill the scheduler thread; the next hour
    retries and nothing user-facing depends on it."""

    class ExplodingStorage(InMemoryStorage):
        async def list_keys(self):
            raise OSError("mount gone")

    db, storage = FakeMediaSession(), ExplodingStorage()
    _wire(monkeypatch, db, storage)

    result = await job.cleanup_media()

    assert result.orphan_files_deleted == 0


@pytest.mark.asyncio
async def test_cleanup_media_on_a_quiet_system_is_two_empty_queries(
    monkeypatch,
):
    """The job is registered unconditionally, not behind the feature
    flag, so it runs on Telegram-only deployments too."""
    db, storage = FakeMediaSession(), InMemoryStorage()
    _wire(monkeypatch, db, storage)

    result = await job.cleanup_media()

    assert (
        result.expired_rows,
        result.expired_files_deleted,
        result.orphan_files_deleted,
    ) == (0, 0, 0)
