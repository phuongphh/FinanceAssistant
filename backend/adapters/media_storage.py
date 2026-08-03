"""Filesystem implementation of :class:`~backend.ports.media_storage.MediaStorage`.

Phase 5.1 #1.2, storage v1. One flat directory of files named by
``storage_key``. No subdirectory fan-out: the population is short-lived
by construction (default TTL 15 minutes, hourly sweep), so the directory
holds tens of files at steady state and the ext4/APFS penalty for a flat
layout never arrives.

Blocking file I/O runs on a worker thread via ``asyncio.to_thread``.
Reading 200KB off local disk is fast, but "fast" on the event loop still
means every other in-flight request waits, and this code path sits behind
a public endpoint.

**Keys are validated, not trusted.** ``storage_key`` comes from the
service (a uuid4 hex) and never from a URL, but the whole point of this
class is that it's the last thing standing between a key and the
filesystem — so a key that isn't 32 lowercase hex characters is refused
outright rather than joined onto a path. That closes traversal
(``../../etc/passwd``), absolute paths, and empty names in one check
instead of three.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from backend.ports.media_storage import StoredObject

logger = logging.getLogger(__name__)

# uuid4().hex — exactly what backend.services.media_url_service generates.
_KEY_RE = re.compile(r"^[0-9a-f]{32}$")


class InvalidStorageKey(ValueError):
    """A key that would not be safe to turn into a path."""


def _validate(key: str) -> str:
    if not isinstance(key, str) or not _KEY_RE.match(key):
        # The key is not user input today, so reaching here is a bug in
        # our code, not an attack. Fail loudly rather than sanitising —
        # a silently-rewritten key would store bytes nobody can find.
        raise InvalidStorageKey("storage_key must be 32 lowercase hex chars")
    return key


class FilesystemMediaStorage:
    """Store media bytes as files under ``root``.

    ``root`` is created on first write rather than at construction, so
    importing this module on a Telegram-only deployment doesn't leave a
    stray directory on disk.
    """

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)

    @property
    def root(self) -> Path:
        return self._root

    def _path(self, key: str) -> Path:
        return self._root / _validate(key)

    # ------------------------------------------------------------------
    # MediaStorage protocol
    # ------------------------------------------------------------------

    async def write(self, key: str, data: bytes) -> None:
        path = self._path(key)
        await asyncio.to_thread(self._write_sync, path, data)

    @staticmethod
    def _write_sync(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temp file in the same directory, then rename. A
        # reader either sees no file or sees the whole thing — never the
        # first half of a chart. The rename is atomic because both paths
        # are on the same filesystem.
        fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".part")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            os.replace(tmp_name, path)
        except BaseException:
            # Best effort: a stray .part file is invisible to list_keys
            # (it fails key validation) so it can't be mistaken for an
            # orphaned object, but leaving it is still litter.
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    async def read(self, key: str) -> bytes | None:
        path = self._path(key)
        return await asyncio.to_thread(self._read_sync, path)

    @staticmethod
    def _read_sync(path: Path) -> bytes | None:
        try:
            return path.read_bytes()
        except FileNotFoundError:
            return None
        except OSError:
            logger.exception("media-storage: read failed")
            return None

    async def delete(self, key: str) -> bool:
        path = self._path(key)
        return await asyncio.to_thread(self._delete_sync, path)

    @staticmethod
    def _delete_sync(path: Path) -> bool:
        try:
            path.unlink()
            return True
        except FileNotFoundError:
            # The cleanup job deletes the same key on every run until the
            # row is swept; "already gone" is the expected steady state.
            return False
        except OSError:
            logger.exception("media-storage: delete failed")
            return False

    async def list_keys(self) -> list[StoredObject]:
        return await asyncio.to_thread(self._list_keys_sync, self._root)

    @staticmethod
    def _list_keys_sync(root: Path) -> list[StoredObject]:
        if not root.is_dir():
            return []
        found: list[StoredObject] = []
        for entry in root.iterdir():
            if not entry.is_file() or not _KEY_RE.match(entry.name):
                # Skips .part files mid-write and anything an operator
                # dropped in the directory by hand. The sweep deletes
                # what it lists, so listing only what we recognise is
                # what keeps it from deleting someone's notes.
                continue
            try:
                mtime = entry.stat().st_mtime
            except OSError:
                continue
            found.append(
                StoredObject(
                    key=entry.name,
                    modified_at=datetime.fromtimestamp(mtime, tz=timezone.utc),
                )
            )
        return found
