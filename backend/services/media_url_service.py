"""Short-lived public URLs for private images (Phase 5.1 #1.2).

Telegram accepts image *bytes*; Zalo accepts a *URL* it fetches itself.
So every chart bound for Zalo has to be reachable, without auth, by
whatever machine Zalo sends. This module mints those URLs and resolves
them back to bytes.

The security model in one line: **the URL is the credential.** There is
no session, no header, no signature — possession of the token is the
whole authorisation. Everything below follows from taking that
seriously:

* The token is 32 random bytes from :mod:`secrets` (~256 bits,
  url-safe-encoded). Not guessable, not enumerable, not derived from
  ``user_id`` or a timestamp.
* The database stores ``sha256(token)`` only. A dump of
  ``media_objects`` yields byte sizes and timestamps but no working URL.
* Default TTL is 15 minutes. A URL that leaks — forwarded screenshot,
  proxy log, Zalo's own cache — is worth something for minutes.
* :func:`resolve` answers ``None`` identically for expired, revoked,
  unknown, and malformed tokens. The router turns all four into the same
  404, so the endpoint can't be used as an oracle for which tokens exist.

Contract with the layer rules
-----------------------------
Flush-only, no commit, no env reads. TTL and storage backend are passed
in from the edge (router / job / notifier), which is what keeps this
module testable without a settings object and lets the Mini App in 5.2
reuse it with a different TTL.

Ordering hazard — read before calling :func:`publish`
-----------------------------------------------------
``publish`` writes the bytes to storage immediately but only *flushes*
the row; the row becomes visible to other transactions when the caller
commits. Two consequences, both real:

1. **A rollback strands the file.** The row never lands, so no row-driven
   cleanup will ever find those bytes. This is accepted deliberately —
   the alternative (row first, bytes written at the edge after commit)
   would hand Zalo a URL whose bytes aren't on disk yet, which is a
   user-visible broken image instead of an invisible few hundred KB.
   :mod:`backend.jobs.cleanup_media` closes the gap from the storage
   side: it lists storage, asks the DB about each key, and deletes what
   nothing points at.

2. **Callers MUST commit before handing the URL to a third party.** Zalo
   fetches the URL within seconds of receiving it. If the worker hasn't
   committed yet, the resolver sees no committed row and returns 404 —
   the image silently fails. Publish, commit, *then* send.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.media_object import MediaObject
from backend.ports.media_storage import MediaStorage

logger = logging.getLogger(__name__)

# Bytes of entropy in a token before encoding. 32 → ~43 url-safe chars.
TOKEN_BYTES = 32

# Used when a caller passes no TTL. Callers that care (the notifier, the
# Mini App) pass their own; this is the "don't think about it" default,
# and it is short on purpose.
DEFAULT_TTL_SECONDS = 15 * 60

# A published object larger than this is a bug upstream (charts are
# ~200KB). Refusing here keeps one runaway render from filling the disk
# that also holds Postgres.
MAX_BYTES = 8 * 1024 * 1024


class MediaTooLarge(ValueError):
    """Payload exceeds :data:`MAX_BYTES`."""


@dataclass(frozen=True)
class PublishedMedia:
    """What :func:`publish` gives back.

    The token is returned rather than a full URL because the service
    doesn't know the public base URL — that is an env value, and reading
    env here would break the layer contract. The edge joins the two.
    """

    token: str
    storage_key: str
    expires_at: datetime


@dataclass(frozen=True)
class ResolvedMedia:
    """What :func:`resolve` gives back on a hit.

    Carries ``content_type`` alongside the bytes: the phase doc sketches
    ``resolve(token) -> bytes | None``, but the router has to set a
    response ``media_type`` and the only place that knows it is the row.
    Returning a pair beats making the router re-query for one column.
    """

    data: bytes
    content_type: str
    byte_size: int


def _hash_token(token: str) -> str:
    """sha256 hex of the token. The only direction we ever compute."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def publish(
    db: AsyncSession,
    storage: MediaStorage,
    *,
    user_id: UUID,
    data: bytes,
    content_type: str,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> PublishedMedia:
    """Store ``data`` and mint a one-off token for it.

    Two calls with identical bytes produce two independent tokens and
    two independent files. That is intentional: deduplicating by content
    hash would make one user's URL resolve to a row another user owns,
    and it would let an attacker who guesses the plaintext confirm that
    someone else published it.

    Flushes so the row gets an ``id`` and any constraint violation
    surfaces here rather than at the caller's commit. Does **not**
    commit — see the module docstring for why that ordering matters.
    """
    if len(data) > MAX_BYTES:
        raise MediaTooLarge(
            f"media payload {len(data)} bytes exceeds limit {MAX_BYTES}"
        )
    if ttl_seconds <= 0:
        raise ValueError("ttl_seconds must be positive")

    token = secrets.token_urlsafe(TOKEN_BYTES)
    storage_key = uuid.uuid4().hex
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)

    # Bytes first. If storage fails we raise before a row exists, which
    # is the harmless direction — a row pointing at nothing would serve
    # a 404 through a URL we'd already promised was good.
    await storage.write(storage_key, data)

    row = MediaObject(
        user_id=user_id,
        token_hash=_hash_token(token),
        content_type=content_type,
        byte_size=len(data),
        storage_key=storage_key,
        expires_at=expires_at,
    )
    db.add(row)
    await db.flush()

    # No token, no hash, no storage_key in the log line: this record
    # exists to answer "are we publishing more than we expect", and
    # anything identifying would turn the log into a second copy of the
    # credential.
    logger.info(
        "media.publish user_id=%s bytes=%d ttl=%ds",
        user_id,
        len(data),
        ttl_seconds,
    )
    return PublishedMedia(
        token=token, storage_key=storage_key, expires_at=expires_at
    )


async def resolve(
    db: AsyncSession,
    storage: MediaStorage,
    *,
    token: str,
) -> ResolvedMedia | None:
    """Return the bytes behind ``token``, or None.

    None covers every failure — unknown token, expired, soft-deleted,
    empty string, bytes missing from storage. The caller must not
    distinguish them in its response; see #1.3.
    """
    if not token:
        return None

    now = datetime.now(timezone.utc)
    stmt = select(MediaObject).where(
        MediaObject.token_hash == _hash_token(token),
        MediaObject.deleted_at.is_(None),
        MediaObject.expires_at > now,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        # Deliberately one log line for four distinct causes. Splitting
        # them would give an attacker with log access the oracle the
        # HTTP surface refuses to be.
        logger.info("media.resolve miss")
        return None

    data = await storage.read(row.storage_key)
    if data is None:
        # Live row, no bytes. Either the cleanup job deleted the file
        # before its own commit landed, or someone emptied the media
        # directory. Worth a warning — this one is our bug, not a
        # visitor's bad token.
        logger.warning(
            "media.resolve row without bytes id=%s user_id=%s",
            row.id,
            row.user_id,
        )
        return None

    return ResolvedMedia(
        data=data, content_type=row.content_type, byte_size=row.byte_size
    )


def build_url(base_url: str, token: str) -> str:
    """Join the public base URL and a token into the URL we hand out.

    Lives here so the path shape is defined once, next to the token that
    fills it, rather than being spelled out in the notifier and again in
    the router. ``base_url`` comes from settings at the edge.
    """
    return f"{base_url.rstrip('/')}/api/v1/media/{token}"
