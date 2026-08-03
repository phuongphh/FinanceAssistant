"""Public media serving endpoint (Phase 5.1 #1.3).

``GET /api/v1/media/{token}`` — the one unauthenticated, non-webhook
route in the app. Zalo's fetcher has no account with us and no way to
carry a header, so the token in the path is the entire authorisation.

Everything here exists to keep that from being worse than it sounds:

**One 404, four causes.** Unknown token, expired token, revoked token,
and bytes-missing all produce a byte-identical response. A different
status, a different body, or a different latency for "expired" versus
"never existed" would turn this route into an oracle: an attacker
holding a stale URL could confirm the account still exists, and anyone
brute-forcing could tell "wrong" from "used to be right". The service
already collapses the four into ``None``; this module's job is to not
un-collapse them.

**Never cached, never sniffed.** ``Cache-Control: no-store`` keeps a
private chart out of every proxy between us and Zalo — the URL is only
alive for minutes, but a cache entry outlives the token. ``X-Content-
Type-Options: nosniff`` stops a browser from re-interpreting PNG bytes
as something executable if a caller ever manages to publish the wrong
content type.

**Rate limited per IP.** Not because brute force is plausible (256-bit
tokens are not guessable) but because an unauthenticated endpoint that
returns hundreds of KB is a bandwidth relay if left uncapped.

**Off by default.** ``MEDIA_URL_ENABLED=false`` leaves the router
unmounted in :mod:`backend.main`, so this file is inert on the current
Telegram-only deployment.

Layer note: this is the edge, so this is where env is read (base path,
TTL, storage root) and handed down to the flush-only service. The
service itself reads none of it.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.adapters.media_storage import FilesystemMediaStorage
from backend.config import get_settings
from backend.database import get_db
from backend.ports.media_storage import MediaStorage
from backend.services import media_url_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/media", tags=["media"])

# Identical body for every miss. A constant, not a formatted string, so
# no future edit can accidentally make one branch's 404 distinguishable
# from another's.
_NOT_FOUND_DETAIL = "not found"

_rate_windows: dict[str, deque[float]] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    """Same derivation as the admin limiter in :mod:`backend.main` —
    trust the first ``X-Forwarded-For`` hop because a reverse proxy
    terminates TLS in front of us."""
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def _rate_limited(ip: str, limit_per_minute: int) -> bool:
    """Sliding 60s window per IP, process-local.

    Deliberately the same shape as the admin limiter rather than a new
    dependency. Production terminates at Caddy, which is the real
    enforcement point; this is the backstop that holds in dev and during
    a proxy misconfiguration.
    """
    now = time.monotonic()
    window = _rate_windows[ip]
    cutoff = now - 60
    while window and window[0] <= cutoff:
        window.popleft()
    if len(window) >= limit_per_minute:
        return True
    window.append(now)
    return False


def get_media_storage() -> MediaStorage:
    """Storage backend for this process.

    A FastAPI dependency so tests can override it with an in-memory
    fake, and so swapping the filesystem for object storage in a later
    phase touches this function and nothing else.
    """
    return FilesystemMediaStorage(get_settings().media_storage_path)


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_DETAIL
    )


@router.get("/{token}")
async def get_media(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    storage: MediaStorage = Depends(get_media_storage),
) -> Response:
    """Serve the bytes behind ``token``, or 404.

    No auth by design — see the module docstring. The only thing that
    distinguishes callers is the token they hold.
    """
    settings = get_settings()

    if _rate_limited(_client_ip(request), settings.media_rate_limit_per_minute):
        # 429 rather than 404: this is a statement about the caller's
        # request rate, not about whether the token exists, so it leaks
        # nothing an unauthenticated visitor didn't already supply.
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too many requests",
        )

    resolved = await media_url_service.resolve(db, storage, token=token)
    if resolved is None:
        raise _not_found()

    return Response(
        content=resolved.data,
        media_type=resolved.content_type,
        headers={
            # Private financial data behind a short-lived credential —
            # nothing between us and the client may keep a copy.
            "Cache-Control": "no-store, private",
            "X-Content-Type-Options": "nosniff",
            # No Content-Disposition: Zalo renders the response inline
            # and a filename would only add a third place where a
            # user-identifying string could leak. Content-Length is left
            # to Starlette, which measures the body — the row's
            # ``byte_size`` is a record of what we stored, and a
            # header that disagreed with the body by even one byte
            # would truncate the image.
        },
    )
