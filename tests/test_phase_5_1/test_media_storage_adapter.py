"""Phase 5.1 #1.2 — the filesystem storage adapter.

Two things are worth testing on a class this thin, and neither is
"can it write a file".

**Key validation.** This adapter is the last thing between a
``storage_key`` and a real path. Keys come from ``uuid4().hex`` today,
but "today" is not a security boundary, so the regex is the boundary and
it is tested against the paths an attacker would try.

**What ``list_keys`` refuses to see.** The cleanup job *deletes what
this method lists*. Listing a half-written temp file, or a file an
operator dropped in the directory, would mean deleting it.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from backend.adapters.media_storage import (
    FilesystemMediaStorage,
    InvalidStorageKey,
)


def _key() -> str:
    return uuid4().hex


# ---------------------------------------------------------------------
# Key validation
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_key",
    [
        "../../etc/passwd",
        "..",
        "/etc/passwd",
        "sub/dir/key",
        "",
        "ABCDEF0123456789abcdef0123456789",  # uppercase
        "0123456789abcdef",  # too short
        _key() + "0",  # too long
        _key() + ".part",
        "not-hex-not-hex-not-hex-not-hex!",
    ],
)
@pytest.mark.asyncio
async def test_invalid_keys_are_refused_rather_than_sanitised(tmp_path, bad_key):
    """Raising beats rewriting: a silently-corrected key would store
    bytes under a name nothing can look up again."""
    storage = FilesystemMediaStorage(tmp_path)

    for call in (
        storage.write(bad_key, b"x"),
        storage.read(bad_key),
        storage.delete(bad_key),
    ):
        with pytest.raises(InvalidStorageKey):
            await call


@pytest.mark.asyncio
async def test_traversal_key_does_not_touch_the_filesystem(tmp_path):
    outside = tmp_path.parent / "escaped.txt"
    storage = FilesystemMediaStorage(tmp_path / "media")

    with pytest.raises(InvalidStorageKey):
        await storage.write("../escaped.txt", b"pwned")

    assert not outside.exists()


@pytest.mark.asyncio
async def test_non_string_key_is_refused(tmp_path):
    storage = FilesystemMediaStorage(tmp_path)

    with pytest.raises(InvalidStorageKey):
        await storage.read(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------
# Round trip
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_then_read_round_trip(tmp_path):
    storage = FilesystemMediaStorage(tmp_path / "media")
    key = _key()

    await storage.write(key, b"\x89PNG-bytes")

    assert await storage.read(key) == b"\x89PNG-bytes"


@pytest.mark.asyncio
async def test_root_is_created_lazily_on_first_write(tmp_path):
    """Importing this module on a Telegram-only deployment must not
    leave a stray directory behind."""
    root = tmp_path / "media"
    storage = FilesystemMediaStorage(root)
    assert not root.exists()

    await storage.write(_key(), b"x")

    assert root.is_dir()


@pytest.mark.asyncio
async def test_write_leaves_no_temp_file_behind(tmp_path):
    """The atomic-rename write must not litter ``.part`` files."""
    root = tmp_path / "media"
    storage = FilesystemMediaStorage(root)
    key = _key()

    await storage.write(key, b"x" * 1024)

    assert [p.name for p in root.iterdir()] == [key]


@pytest.mark.asyncio
async def test_rewriting_a_key_replaces_the_contents(tmp_path):
    storage = FilesystemMediaStorage(tmp_path)
    key = _key()

    await storage.write(key, b"first")
    await storage.write(key, b"second-and-longer")

    assert await storage.read(key) == b"second-and-longer"


# ---------------------------------------------------------------------
# Missing-key semantics — the cleanup job depends on both of these
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reading_a_missing_key_returns_none(tmp_path):
    storage = FilesystemMediaStorage(tmp_path)

    assert await storage.read(_key()) is None


@pytest.mark.asyncio
async def test_deleting_a_missing_key_returns_false(tmp_path):
    """"Already gone" is the steady state for a job that re-runs hourly,
    so it must not raise."""
    storage = FilesystemMediaStorage(tmp_path)

    assert await storage.delete(_key()) is False


@pytest.mark.asyncio
async def test_delete_is_idempotent(tmp_path):
    storage = FilesystemMediaStorage(tmp_path)
    key = _key()
    await storage.write(key, b"x")

    assert await storage.delete(key) is True
    assert await storage.delete(key) is False


# ---------------------------------------------------------------------
# list_keys — the sweep deletes what this returns
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_keys_on_a_missing_root_is_empty(tmp_path):
    storage = FilesystemMediaStorage(tmp_path / "never-created")

    assert await storage.list_keys() == []


@pytest.mark.asyncio
async def test_list_keys_reports_keys_and_modification_times(tmp_path):
    storage = FilesystemMediaStorage(tmp_path)
    key = _key()
    before = datetime.now(timezone.utc) - timedelta(seconds=5)

    await storage.write(key, b"x")
    listed = await storage.list_keys()

    assert [obj.key for obj in listed] == [key]
    assert listed[0].modified_at > before
    assert listed[0].modified_at.tzinfo is not None


@pytest.mark.asyncio
async def test_list_keys_skips_files_that_are_not_ours(tmp_path):
    """Temp files mid-write and operator-dropped files both fail the key
    regex, which is exactly what keeps the sweep from deleting them."""
    root = tmp_path / "media"
    root.mkdir()
    mine = _key()
    (root / mine).write_bytes(b"x")
    (root / "tmp1234.part").write_bytes(b"half a chart")
    (root / "notes.txt").write_bytes(b"operator notes")
    (root / "0123456789abcdef0123456789abcdef.bak").write_bytes(b"x")
    os.mkdir(root / _key())  # a directory named like a key

    storage = FilesystemMediaStorage(root)

    assert [obj.key for obj in await storage.list_keys()] == [mine]
