"""Hourly sweep of expired media (Phase 5.1 #1.4).

Three passes, and they exist for different reasons.

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
asks the database which keys a *live* row claims, and deletes the rest.
Live rather than any row, so that a file pass 1 failed to unlink gets
collected here instead of surviving forever behind a soft-deleted row
pass 1 will never look at again.

**Pass 3 — temp files.** The filesystem adapter writes to a ``.part``
file and renames it, so a process killed mid-write leaves real image
bytes behind under a name neither pass above will touch. Pass 3 is the
only thing that reclaims them; it is duck-typed off the storage backend
because temp files are a filesystem artefact, not part of the port.

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
    above zero means bytes reached storage that no live row claims —
    usually a publish whose transaction rolled back, occasionally a file
    pass 1 failed to unlink and pass 2 collected on its behalf. Either
    way it is a signal about something going wrong upstream, not about
    media. ``temp_files`` above zero means a process died mid-write.
    Summing them into one number would hide all three.
    """

    expired_rows: int = 0
    expired_files_deleted: int = 0
    orphan_files_deleted: int = 0
    temp_files_deleted: int = 0


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
    #
    # Live rows only. A soft-deleted row is one pass 1 has already
    # handled, and pass 1's query excludes it forever after — so if the
    # file is still on disk, pass 1's ``storage.delete`` failed (a
    # transient EIO, a full disk, a container that died between the
    # commit and the unlink) and nothing will ever retry it. Treating
    # those keys as unclaimed is what makes that failure self-healing
    # instead of permanent.
    claimed = set(
        (
            await db.execute(
                select(MediaObject.storage_key).where(
                    MediaObject.storage_key.in_(candidates),
                    MediaObject.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )

    deleted = 0
    for key in candidates:
        if key in claimed:
            # A live row points at this file. Pass 1 owns it — it will be
            # swept when the row expires, and until then the URL works.
            continue
        if await storage.delete(key):
            deleted += 1
    return deleted


async def _sweep_temp_files(storage: MediaStorage, grace_seconds: int) -> int:
    """Reclaim half-written files the storage backend left behind.

    The filesystem adapter writes to a temp file and renames it, so a
    process killed mid-write leaves a ``.part`` holding real image bytes.
    It is invisible to both passes above by design: no row ever pointed
    at it, and ``list_keys`` refuses to report it precisely so the orphan
    sweep can't delete an in-flight write. That leaves nobody to clean it
    up, which is how private bytes end up living on disk indefinitely.

    Not part of the :class:`~backend.ports.media_storage.MediaStorage`
    protocol: temp files are an artefact of writing to a filesystem, and
    an object-storage backend has no equivalent. The capability is
    duck-typed so this job works against either.
    """
    purge = getattr(storage, "purge_stale_temp_files", None)
    if purge is None:
        return 0
    return await purge(grace_seconds)


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
            result.temp_files_deleted = await _sweep_temp_files(
                storage, settings.media_orphan_grace_seconds
            )
    except Exception:
        # A sweep that fails is not an incident — the next hour retries,
        # and nothing user-facing depends on it. Swallowing keeps one bad
        # run from killing the scheduler thread.
        logger.exception("media-cleanup: sweep failed")
        return result

    logger.info(
        "media-cleanup: expired_rows=%d expired_files=%d orphan_files=%d "
        "temp_files=%d",
        result.expired_rows,
        result.expired_files_deleted,
        result.orphan_files_deleted,
        result.temp_files_deleted,
    )
    if result.orphan_files_deleted:
        # Orphans mean a publish was rolled back, or pass 1 couldn't
        # unlink. Rare and worth noticing; a steady stream of them points
        # at a caller that commits after it can fail, or at storage that
        # is failing writes.
        logger.warning(
            "media-cleanup: %d orphaned file(s) removed — a publish was "
            "rolled back after writing bytes, or an expired file could "
            "not be unlinked",
            result.orphan_files_deleted,
        )
    if result.temp_files_deleted:
        logger.warning(
            "media-cleanup: %d half-written file(s) removed — a process "
            "died between writing and renaming",
            result.temp_files_deleted,
        )
    return result
