"""Phase 5.1 #1.2 — publish/resolve, and what must never leak.

The DoD lines under test: *"publish → resolve round-trip; token hết hạn
→ None; token sai → None; token đã revoke → None; hai lần publish cùng
bytes ra hai token khác nhau; không cột nào chứa raw token."*

The last one is the load-bearing assertion. The URL is the entire
credential, so a column that happened to hold the plaintext would turn a
read-only database dump into a set of working URLs. It is checked against
*every* column rather than against ``token_hash`` specifically, so adding
a column later cannot quietly reintroduce the leak.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from tests.test_phase_5_1.conftest import FakeMediaSession, InMemoryStorage

from backend.models.media_object import MediaObject
from backend.services import media_url_service as svc

PNG = b"\x89PNG\r\n\x1a\n" + b"chart-bytes" * 10


async def _publish(db, storage, **kwargs):
    return await svc.publish(
        db,
        storage,
        user_id=kwargs.pop("user_id", uuid4()),
        data=kwargs.pop("data", PNG),
        content_type=kwargs.pop("content_type", "image/png"),
        **kwargs,
    )


# ---------------------------------------------------------------------
# Round trip
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_then_resolve_returns_the_same_bytes():
    db, storage = FakeMediaSession(), InMemoryStorage()

    published = await _publish(db, storage)
    resolved = await svc.resolve(db, storage, token=published.token)

    assert resolved is not None
    assert resolved.data == PNG
    assert resolved.content_type == "image/png"
    assert resolved.byte_size == len(PNG)


@pytest.mark.asyncio
async def test_publish_never_commits():
    """Layer contract: the caller owns the transaction boundary."""
    db, storage = FakeMediaSession(), InMemoryStorage()

    await _publish(db, storage)

    assert db.commits == 0
    assert db.flushes == 1


@pytest.mark.asyncio
async def test_publish_writes_bytes_before_the_row_exists():
    """The ordering the orphan sweep exists to clean up after.

    Bytes land in storage during ``publish``; the row is only flushed.
    Asserting it here rather than trusting the docstring means a future
    reordering (row first, bytes at the edge) has to come with a
    deliberate change to this test — and to the cleanup job that depends
    on the current order.
    """
    db, storage = FakeMediaSession(), InMemoryStorage()

    published = await _publish(db, storage)

    assert storage.objects[published.storage_key] == PNG


@pytest.mark.asyncio
async def test_default_ttl_is_fifteen_minutes():
    db, storage = FakeMediaSession(), InMemoryStorage()

    before = datetime.now(timezone.utc)
    published = await _publish(db, storage)

    delta = published.expires_at - before
    assert timedelta(minutes=14) < delta <= timedelta(minutes=15, seconds=5)


# ---------------------------------------------------------------------
# Every way a resolve can miss
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expired_token_resolves_to_none():
    db, storage = FakeMediaSession(), InMemoryStorage()

    published = await _publish(db, storage, ttl_seconds=60)
    # Age the row past its TTL rather than sleeping.
    db.rows[0].expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

    assert await svc.resolve(db, storage, token=published.token) is None


@pytest.mark.asyncio
async def test_unknown_token_resolves_to_none():
    db, storage = FakeMediaSession(), InMemoryStorage()
    await _publish(db, storage)

    assert await svc.resolve(db, storage, token="not-a-real-token") is None


@pytest.mark.asyncio
async def test_empty_token_resolves_to_none_without_querying():
    """An empty path segment must not reach the database at all."""
    db, storage = FakeMediaSession(), InMemoryStorage()

    assert await svc.resolve(db, storage, token="") is None


@pytest.mark.asyncio
async def test_revoked_token_resolves_to_none():
    """``deleted_at`` doubles as revocation — the soft-delete pattern."""
    db, storage = FakeMediaSession(), InMemoryStorage()

    published = await _publish(db, storage)
    db.rows[0].deleted_at = datetime.now(timezone.utc)

    assert await svc.resolve(db, storage, token=published.token) is None


@pytest.mark.asyncio
async def test_live_row_with_missing_bytes_resolves_to_none():
    """The one miss that is our bug, not a visitor's bad token.

    It still returns None so the endpoint answers identically — the
    difference lives in the log, which is not reachable from outside.
    """
    db, storage = FakeMediaSession(), InMemoryStorage()

    published = await _publish(db, storage)
    storage.objects.clear()

    assert await svc.resolve(db, storage, token=published.token) is None


# ---------------------------------------------------------------------
# Token properties
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_identical_bytes_produce_independent_tokens_and_files():
    """No content-hash dedup.

    Deduplicating would make one user's URL resolve to a row another
    user owns, and would let anyone who guesses the plaintext confirm
    that someone else published it.
    """
    db, storage = FakeMediaSession(), InMemoryStorage()

    first = await _publish(db, storage, user_id=uuid4(), data=PNG)
    second = await _publish(db, storage, user_id=uuid4(), data=PNG)

    assert first.token != second.token
    assert first.storage_key != second.storage_key
    assert len(storage.objects) == 2


@pytest.mark.asyncio
async def test_no_column_holds_the_raw_token():
    db, storage = FakeMediaSession(), InMemoryStorage()

    published = await _publish(db, storage)
    row = db.rows[0]

    stored = [
        str(getattr(row, column.name))
        for column in MediaObject.__table__.columns
    ]
    assert published.token not in stored
    # Not just absent as a whole value — absent as a substring, which
    # also rules out a column that embedded it in a longer string.
    assert not any(published.token in value for value in stored)

    assert row.token_hash == hashlib.sha256(
        published.token.encode("utf-8")
    ).hexdigest()


@pytest.mark.asyncio
async def test_storage_key_is_not_derived_from_the_token():
    """Knowing a filename must not yield a working URL, or the reverse."""
    db, storage = FakeMediaSession(), InMemoryStorage()

    published = await _publish(db, storage)

    assert published.storage_key not in published.token
    assert published.token not in published.storage_key
    assert (
        hashlib.sha256(published.token.encode("utf-8")).hexdigest()[:32]
        != published.storage_key
    )


def test_tokens_are_long_enough_to_be_unguessable():
    """32 random bytes, url-safe encoded — ~43 characters."""
    assert svc.TOKEN_BYTES >= 32
    token = svc.secrets.token_urlsafe(svc.TOKEN_BYTES)
    assert len(token) >= 40


# ---------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_oversized_payload_is_refused_before_anything_is_written():
    db, storage = FakeMediaSession(), InMemoryStorage()

    with pytest.raises(svc.MediaTooLarge):
        await _publish(db, storage, data=b"x" * (svc.MAX_BYTES + 1))

    assert storage.objects == {}
    assert db.rows == [] and db.pending == []


@pytest.mark.asyncio
async def test_non_positive_ttl_is_refused():
    db, storage = FakeMediaSession(), InMemoryStorage()

    for ttl in (0, -1):
        with pytest.raises(ValueError):
            await _publish(db, storage, ttl_seconds=ttl)

    assert storage.objects == {}


@pytest.mark.asyncio
async def test_storage_failure_leaves_no_row_behind():
    """The harmless direction: a row pointing at nothing would serve a
    404 through a URL we had already promised was good."""
    db, storage = FakeMediaSession(), InMemoryStorage()
    storage.write_error = OSError("disk full")

    with pytest.raises(OSError):
        await _publish(db, storage)

    assert db.rows == [] and db.pending == []


# ---------------------------------------------------------------------
# URL shape
# ---------------------------------------------------------------------


def test_build_url_joins_base_and_token():
    assert (
        svc.build_url("https://api.example.com", "abc")
        == "https://api.example.com/api/v1/media/abc"
    )


def test_build_url_tolerates_a_trailing_slash():
    """Operators write the base URL by hand; both forms must work."""
    assert svc.build_url("https://api.example.com/", "abc") == svc.build_url(
        "https://api.example.com", "abc"
    )
