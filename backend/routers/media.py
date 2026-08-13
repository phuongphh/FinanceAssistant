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
from backend.utils.client_ip import client_ip

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/media", tags=["media"])

# Identical body for every miss. A constant, not a formatted string, so
# no future edit can accidentally make one branch's 404 distinguishable
# from another's.
_NOT_FOUND_DETAIL = "not found"

_rate_windows: dict[str, deque[float]] = defaultdict(deque)

# The windows above are process-local state keyed by client IP, and this
# is a public route. The key is no longer freely caller-supplied — the
# forwarded header is only believed from a trusted proxy peer — but a
# real proxy still forwards an unbounded number of distinct clients, so
# without eviction the dict only ever grows. Two bounds, in order:
#
#   * a window whose newest hit is older than the 60s sliding window can
#     never affect a decision again, so it is dropped;
#   * if that still leaves more than ``_MAX_TRACKED_IPS`` distinct
#     clients inside one minute, the least recently active are dropped
#     too. That hands a few callers a fresh allowance, which is the
#     right trade: at that volume the real enforcement point is Caddy in
#     front of us, and this backstop's job is to not fall over.
_WINDOW_SECONDS = 60
_MAX_TRACKED_IPS = 10_000
_EVICT_INTERVAL_SECONDS = 5.0
_last_evict = float("-inf")


def _now() -> float:
    """Indirection so tests can drive the clock without patching the
    ``time`` module out from under the event loop."""
    return time.monotonic()


def _evict_stale(now: float) -> None:
    """Drop windows that can no longer affect a decision.

    Rate limited itself: sweeping the dict on every request would make
    each request O(tracked IPs). Runs at most every
    ``_EVICT_INTERVAL_SECONDS``, or immediately once the map is over its
    cap — a flood must not be able to outrun the sweep by arriving
    faster than the interval.
    """
    global _last_evict

    over_cap = len(_rate_windows) > _MAX_TRACKED_IPS
    if not over_cap and now - _last_evict < _EVICT_INTERVAL_SECONDS:
        return
    _last_evict = now

    cutoff = now - _WINDOW_SECONDS
    for ip in [
        ip
        for ip, window in _rate_windows.items()
        if not window or window[-1] <= cutoff
    ]:
        del _rate_windows[ip]

    overflow = len(_rate_windows) - _MAX_TRACKED_IPS
    if overflow <= 0:
        return
    oldest = sorted(_rate_windows.items(), key=lambda item: item[1][-1])
    for ip, _ in oldest[:overflow]:
        del _rate_windows[ip]


def _client_ip(request: Request) -> str:
    """Same derivation as the admin limiter in :mod:`backend.main`.

    ``X-Forwarded-For`` is only believed from a peer inside
    ``TRUSTED_PROXY_CIDRS``. This route is the one that needs it most:
    it is public and unauthenticated, so before that rule a direct
    caller could hand itself a fresh window per request by rotating the
    header — see :mod:`backend.utils.client_ip`.
    """
    return client_ip(request)


def _rate_limited(ip: str, limit_per_minute: int) -> bool:
    """Sliding 60s window per IP, process-local.

    Deliberately the same shape as the admin limiter rather than a new
    dependency. Production terminates at Caddy, which is the real
    enforcement point; this is the backstop that holds in dev and during
    a proxy misconfiguration.
    """
    now = _now()
    _evict_stale(now)
    window = _rate_windows[ip]
    cutoff = now - _WINDOW_SECONDS
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
