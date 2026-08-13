"""Media storage port — where the bytes behind a media URL actually live.

Phase 5.1 #1.2. The service owns the *row* (token hash, TTL, ownership);
this port owns the *bytes*. Splitting them is what lets v1 be a directory
on the prod box and v2 be object storage without a single caller
changing — the service only ever holds a ``storage_key``, never a path.

The interface is deliberately four methods. Anything richer (ranges,
signed URLs, metadata) would leak the filesystem's shape into the
service and make the object-storage swap a rewrite instead of a new
class.

``list_keys`` exists only for the orphan sweep in
:mod:`backend.jobs.cleanup_media`: because the service is flush-only,
bytes hit storage before the caller's transaction commits, so a rollback
strands a file that no row will ever point at. The sweep walks storage
and asks the DB about each key it finds — which is impossible without a
listing operation, hence its presence in an otherwise minimal port.
"""
from __future__ import annotations

from datetime import datetime
from typing import NamedTuple, Protocol


class StoredObject(NamedTuple):
    """One item as seen from the storage side, not the DB side.

    ``modified_at`` is what gives the orphan sweep its grace period: a
    file written seconds ago may simply belong to a transaction that
    hasn't committed yet, and deleting it would break a live request.
    """

    key: str
    modified_at: datetime


class MediaStorage(Protocol):
    """Content-addressed-by-key blob storage.

    Implementations MUST be safe to call concurrently and MUST NOT
    raise on a missing key in :meth:`read` or :meth:`delete` — a URL for
    bytes that vanished is a 404, not a 500, and the cleanup job deletes
    the same key twice by design.
    """

    async def write(self, key: str, data: bytes) -> None:
        """Store ``data`` under ``key``, overwriting if it exists."""
        ...

    async def read(self, key: str) -> bytes | None:
        """Return the bytes, or None if the key is unknown."""
        ...

    async def delete(self, key: str) -> bool:
        """Remove ``key``. True if something was removed, False if it
        was already gone. Never raises for a missing key."""
        ...

    async def list_keys(self) -> list[StoredObject]:
        """Every key currently in storage, with its last-write time.

        Only the orphan sweep calls this. Object-storage implementations
        should paginate internally rather than exposing a cursor — the
        expected population is hundreds of short-lived files, not
        millions.
        """
        ...
