"""Hourly sweep of expired media (Phase 5.1 #1.4).

Two passes, and they exist for different reasons.

**Pass 1 — row-driven.** Every live ``media_objects`` row past its
``expires_at`` gets soft-deleted and its file removed. This is the
ordinary case: a chart was published, Zalo fetched it, fifteen minutes
went by. Without this pass the disk grows monotonically and expired rows
accumulate in the index the resolver reads.

**Pass 2 — storage-driven (the orphan sweep).** This one is the
consequence of a layer rule.
:mod:`backend.services.media_url_service` is flush-only, so ``publish``
writes bytes to storage *before* the caller's transaction commits. If
that transaction rolls back, the file is on disk and no row will ever
point at it — invisible to pass 1 forever. So pass 2 walks storage,
asks the database which keys it knows about, and deletes the rest.

The alternative design (row first, bytes written at the edge after
commit) would remove the orphan case entirely, and is cleaner in the
abstract. It was rejected for 5.1 because the notifier hands the URL to
Zalo *before* the worker commits at the transaction boundary, so
row-first would hand out a URL whose bytes weren't on disk yet: an
invisible few hundred KB of litter is a cheaper failure than a broken
image in a user's chat. Revisit if the notifier ever gains its own
commit.

Ordering within pass 1
----------------------
Soft-delete the rows, commit, *then* delete the files. A failed commit
after the files are gone would leave live rows pointing at nothing —
the resolver's "row without bytes" warning, and a broken image for
anyone still holding the URL. The reverse (rows marked deleted, files
still present) is self-healing: pass 2 collects them on the next run.

Idempotency
-----------
Running twice back to back is a no-op the second time. The row query
excludes already-swept rows; storage deletes return False for a missing
file rather than raising.

Grace period
------------
An orphan is only deleted after
``MEDIA_ORPHAN_GRACE_SECONDS`` (default 1h) of no writes. A file written
seconds ago may belong to a transaction that hasn't committed yet, and
deleting it would break a request that is still in flight. The grace
period is read here, at the job's edge — not in the service.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from backend.adapters.media_storage import FilesystemMediaStorage
from backend.config import get_settings
from backend.database import get_session_factory
from backend.models.media_object import MediaObject
from backend.ports.media_storage import MediaStorage

logger = logging.getLogger(__name__)

# Rows handled per run. A cap rather than "everything" so one pathological
# backlog can't hold a transaction open for minutes; the next hourly run
# picks up the remainder.
BATCH_LIMIT = 5000


@dataclass
class CleanupResult:
    """Counts, reported separately on purpose.

    ``expired_rows`` trending up with traffic is healthy. ``orphan_files``
    above zero means transactions are rolling back after publish — a
    signal about upstream code, not about media. Summing them into one
    number would hide that.
    """

    expired_rows: int = 0
    expired_files_deleted: int = 0
    orphan_files_deleted: int = 0


async def _sweep_expired(db, storage: MediaStorage) -> tuple[int, int]:
    """Soft-delete expired rows and remove their files."""
    now = datetime.now(timezone.utc)

    stmt = (
        select(MediaObject.id, MediaObject.storage_key)
        .where(
            MediaObject.deleted_at.is_(None),
            MediaObject.expires_at <= now,
        )
        .limit(BATCH_LIMIT)
    )
    rows = (await db.execute(stmt)).all()
    if not rows:
        return 0, 0

    ids = [row.id for row in rows]
    await db.execute(
        update(MediaObject)
        .where(MediaObject.id.in_(ids))
        .values(deleted_at=now)
    )
    # Commit before touching the filesystem: see the module docstring on
    # ordering. This job owns its own session, so committing here is the
    # job acting as its own transaction boundary, not a service reaching
    # past its layer.
    await db.commit()

    deleted = 0
    for row in rows:
        if await storage.delete(row.storage_key):
            deleted += 1
    return len(ids), deleted


async def _sweep_orphans(db, storage: MediaStorage, grace_seconds: int) -> int:
    """Delete files older than the grace period that no row claims."""
    stored = await storage.list_keys()
    if not stored:
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=grace_seconds)
    candidates = [obj.key for obj in stored if obj.modified_at < cutoff]
    if not candidates:
        return 0

    # Ask about the candidates only. Selecting every key in the table
    # would scale with history; this scales with what is actually on
    # disk, which the sweep itself keeps small.
    known = set(
        (
            await db.execute(
                select(MediaObject.storage_key).where(
                    MediaObject.storage_key.in_(candidates)
                )
            )
        )
        .scalars()
        .all()
    )

    deleted = 0
    for key in candidates:
        if key in known:
            # A row exists — pass 1 owns this file, whether it is live or
            # already soft-deleted. Not an orphan.
            continue
        if await storage.delete(key):
            deleted += 1
    return deleted


async def cleanup_media() -> CleanupResult:
    """Entry point registered with the scheduler. Never raises."""
    result = CleanupResult()
    settings = get_settings()
    storage = FilesystemMediaStorage(settings.media_storage_path)
    session_factory = get_session_factory()

    try:
        async with session_factory() as db:
            result.expired_rows, result.expired_files_deleted = (
                await _sweep_expired(db, storage)
            )
            result.orphan_files_deleted = await _sweep_orphans(
                db, storage, settings.media_orphan_grace_seconds
            )
    except Exception:
        # A sweep that fails is not an incident — the next hour retries,
        # and nothing user-facing depends on it. Swallowing keeps one bad
        # run from killing the scheduler thread.
        logger.exception("media-cleanup: sweep failed")
        return result

    logger.info(
        "media-cleanup: expired_rows=%d expired_files=%d orphan_files=%d",
        result.expired_rows,
        result.expired_files_deleted,
        result.orphan_files_deleted,
    )
    if result.orphan_files_deleted:
        # Orphans mean a publish was rolled back. Rare and worth noticing;
        # a steady stream of them points at a caller that commits after
        # it can fail.
        logger.warning(
            "media-cleanup: %d orphaned file(s) removed — a publish was "
            "rolled back after writing bytes",
            result.orphan_files_deleted,
        )
    return result
