"""Zalo OA OAuth token lifecycle (Phase 5.0 #1.3).

Zalo's ``access_token`` lives one hour and its ``refresh_token`` is
**single-use**: every successful refresh rotates it and invalidates the
previous one server-side. That one fact drives every design choice here.

Why this service owns its own session
-------------------------------------
CLAUDE.md forbids ``db.commit()`` in the service layer, because the
router/worker owns the transaction boundary. This module is a deliberate,
narrow exception and it is safe precisely *because* it never accepts a
caller's session: it opens short-lived sessions from
:func:`backend.database.get_session_factory` and commits inside them.

The exception is unavoidable. The write-ahead protocol needs a commit
*between* two steps (see below) — a refresh executed inside an ambient
request transaction would either lose the write-ahead marker on rollback
or force a caller's unrelated work to commit early. Treat this like a
worker that happens to be reachable from anywhere, not like a service.

**Never** add an ``db: AsyncSession`` parameter to a public function here.

The write-ahead refresh protocol
--------------------------------
A plain "call Zalo, then save the result" is unsafe: Zalo invalidates the
old refresh token the moment the HTTP call succeeds, so a crash between
response and commit destroys the only usable token and a human has to
re-authorise the OA by hand. A DB transaction does not help — the damage
is on Zalo's side, outside it. So (per
``docs/conventions/zalo-operations.md`` §Token refresh protocol)::

    1. pg_advisory_xact_lock(app_id)   -- only one refresher at a time
    2. re-read the row                  -- someone may have refreshed already
    3. COMMIT refresh_pending = {token, attempted_at}
    4. POST /v4/oa/access_token
    5. COMMIT new pair, refresh_pending = NULL

Two consequences worth stating out loud:

* **The refresh POST is never retried.** Everywhere else in this codebase
  a transient network error is retried with backoff; here a retry can burn
  a token whose first attempt actually succeeded but whose response was
  lost. One attempt, then fail loudly.
* **A ``refresh_pending`` row is never blind-retried.** We cannot know
  whether Zalo consumed the token, so the service logs ``CRITICAL
  zalo.token.refresh_pending`` and raises, pointing at the runbook.

Performance
-----------
Every outbound Zalo message needs a token. A DB round trip per send would
put ~1-3ms and a pool checkout on the hot path for a value that changes
once an hour, so a valid token is cached in-process. The cache is a
read-through optimisation only — correctness never depends on it, and
``force_refresh`` bypasses it.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.database import get_session_factory
from backend.models.zalo_oa_credential import ZaloOACredential

logger = logging.getLogger(__name__)

REFRESH_URL = "https://oauth.zaloapp.com/v4/oa/access_token"

# Refresh once the token has less than this left. Five minutes comfortably
# covers a slow refresh plus the longest send retry chain, so no request
# ever picks up a token that expires while it is in flight.
REFRESH_SKEW = timedelta(minutes=5)

# How long a ``refresh_pending`` marker is assumed to belong to a refresh
# that is still running in another process. Beyond this it is treated as a
# crash: the runbook, not a retry. The refresh POST timeout is 10s, so 60s
# is ~6x headroom while still surfacing a real crash within a minute.
IN_FLIGHT_GRACE = timedelta(seconds=60)

# One attempt. See the module docstring for why there is no retry loop.
_REFRESH_TIMEOUT_SECONDS = 10.0

RUNBOOK = "docs/conventions/zalo-operations.md#runbook-refresh_pending-found-on-startup"


class ZaloTokenError(RuntimeError):
    """Base class — callers that only care about 'no token' catch this."""


class ZaloTokenMissing(ZaloTokenError):
    """No credential row, or the row has nothing usable in it.

    Recoverable by an operator running ``scripts/seed_zalo_credentials.py``.
    """


class ZaloTokenRefreshInFlight(ZaloTokenError):
    """Another process is mid-refresh right now. Transient — retry shortly."""


class ZaloTokenRefreshStuck(ZaloTokenError):
    """A ``refresh_pending`` marker outlived its grace period.

    Means a process died between steps 3 and 5 and we cannot know whether
    Zalo consumed the token. Requires the manual runbook; never retried.
    """


class ZaloTokenRefreshFailed(ZaloTokenError):
    """The refresh call itself failed. ``refresh_pending`` is left set."""


@dataclass(frozen=True)
class _CachedToken:
    token: str
    expires_at: datetime


# ---------------------------------------------------------------------------
# Process-local state
# ---------------------------------------------------------------------------

# Read-through cache, keyed by app_id. Never authoritative.
_cache: dict[str, _CachedToken] = {}

# One refresh at a time *within* this process. pg_advisory_xact_lock covers
# the cross-process case; this lock stops N coroutines in the same process
# from all queueing on Postgres for a refresh only one of them needs.
_locks: dict[str, asyncio.Lock] = {}
_locks_guard = asyncio.Lock()

_http_client: httpx.AsyncClient | None = None
_http_client_guard = asyncio.Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    """Postgres gives us tz-aware values; hand-built rows may not be."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


async def _lock_for(app_id: str) -> asyncio.Lock:
    async with _locks_guard:
        lock = _locks.get(app_id)
        if lock is None:
            lock = asyncio.Lock()
            _locks[app_id] = lock
        return lock


async def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        async with _http_client_guard:
            if _http_client is None:
                _http_client = httpx.AsyncClient(timeout=_REFRESH_TIMEOUT_SECONDS)
    return _http_client


async def close_http_client() -> None:
    """Release the refresh client. Call from the app lifespan shutdown."""
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


def _advisory_key(app_id: str) -> int:
    """Stable signed bigint for ``pg_advisory_xact_lock``.

    ``hash()`` is randomised per process (PYTHONHASHSEED), so two workers
    would lock different keys and both refresh. Digest instead.
    """
    digest = hashlib.sha256(app_id.encode("utf-8")).digest()[:8]
    return int.from_bytes(digest, "big", signed=True)


async def _acquire_advisory_lock(db: AsyncSession, app_id: str) -> None:
    """Serialise refreshers across processes for the rest of this txn.

    No-op outside Postgres so the protocol stays testable; the in-process
    :data:`_locks` still provides mutual exclusion there.
    """
    bind = db.get_bind() if hasattr(db, "get_bind") else None
    dialect = getattr(getattr(bind, "dialect", None), "name", "postgresql")
    if dialect != "postgresql":
        return
    await db.execute(
        text("SELECT pg_advisory_xact_lock(:key)"), {"key": _advisory_key(app_id)}
    )


def _is_fresh(expires_at: datetime | None, *, now: datetime) -> bool:
    """NULL ``expires_at`` counts as expired.

    One wasted refresh beats an hour of failing sends against a token we
    only *assumed* was good.
    """
    expires_at = _as_utc(expires_at)
    if expires_at is None:
        return False
    return expires_at - now > REFRESH_SKEW


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def get_access_token(app_id: str | None = None) -> str:
    """Return a usable access token, refreshing it if it is close to expiry.

    Raises a :class:`ZaloTokenError` subclass rather than returning an
    empty string: a caller that silently sends with no token would get an
    opaque platform error instead of an actionable one.
    """
    app_id = _resolve_app_id(app_id)

    cached = _cache.get(app_id)
    if cached is not None and _is_fresh(cached.expires_at, now=_now()):
        return cached.token

    return await _ensure_token(app_id, force=False, stale_token=None)


async def force_refresh(app_id: str | None = None, *, stale_token: str = "") -> str:
    """Refresh even if ``expires_at`` says the token is still good.

    Called by the OA adapter when Zalo answers ``-216``/``-201``
    (token expired) earlier than our own bookkeeping expected.

    ``stale_token`` is the token that just failed. If the stored token has
    already moved past it, another caller has refreshed and we hand back
    the new one instead of burning a second refresh — the common case when
    several concurrent sends all hit ``-216`` together.
    """
    app_id = _resolve_app_id(app_id)
    _cache.pop(app_id, None)
    return await _ensure_token(app_id, force=True, stale_token=stale_token or None)


async def peek_credential(app_id: str | None = None) -> dict[str, object]:
    """Read-only credential health, for the startup scan and ops endpoints.

    Deliberately returns no token material — only whether one exists.
    """
    app_id = _resolve_app_id(app_id)
    factory = get_session_factory()
    async with factory() as db:
        row = await db.get(ZaloOACredential, app_id)
        if row is None:
            return {"app_id": app_id, "exists": False}
        return {
            "app_id": app_id,
            "exists": True,
            "has_access_token": bool(row.access_token),
            "has_refresh_token": bool(row.refresh_token),
            "expires_at": _as_utc(row.expires_at),
            "refresh_pending": bool(row.refresh_pending_token),
            "refresh_pending_at": _as_utc(row.refresh_pending_at),
            "refresh_count": row.refresh_count,
            "last_refreshed_at": _as_utc(row.last_refreshed_at),
        }


def reset_cache_for_tests() -> None:
    """Drop process-local state. Tests only."""
    _cache.clear()
    _locks.clear()


def _resolve_app_id(app_id: str | None) -> str:
    resolved = app_id or get_settings().zalo_app_id
    if not resolved:
        raise ZaloTokenMissing(
            "ZALO_APP_ID is not configured — cannot identify which OA "
            "credential to use."
        )
    return resolved


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


async def _ensure_token(app_id: str, *, force: bool, stale_token: str | None) -> str:
    lock = await _lock_for(app_id)
    async with lock:
        # Re-check under the lock: while we queued, the coroutine ahead of
        # us very likely did the refresh we were about to duplicate.
        cached = _cache.get(app_id)
        if cached is not None and _is_fresh(cached.expires_at, now=_now()):
            if not force or (stale_token and cached.token != stale_token):
                return cached.token

        pending_token, early = await _begin_refresh(
            app_id, force=force, stale_token=stale_token
        )
        if early is not None:
            return early

        payload = await _post_refresh(app_id, pending_token)
        return await _finish_refresh(app_id, payload)


async def _begin_refresh(
    app_id: str, *, force: bool, stale_token: str | None
) -> tuple[str, str | None]:
    """Steps 1-3: lock, re-read, write-ahead the pending marker, COMMIT.

    Returns ``(refresh_token_to_use, early_result)``. When ``early_result``
    is not None the stored token turned out to be usable and no HTTP call
    should happen.
    """
    factory = get_session_factory()
    async with factory() as db:
        # 1 — only one refresher at a time, released when this txn ends.
        await _acquire_advisory_lock(db, app_id)

        # 2 — re-read *after* the lock. Reading before it would be reading
        # exactly the state the lock exists to protect us from.
        row = await db.get(ZaloOACredential, app_id)
        if row is None:
            raise ZaloTokenMissing(
                f"No zalo_oa_credentials row for app_id={app_id}. "
                "Seed one with scripts/seed_zalo_credentials.py."
            )

        _guard_pending(app_id, row)

        now = _now()
        usable = _token_already_usable(row, force=force, stale_token=stale_token, now=now)
        if usable is not None:
            _cache[app_id] = _CachedToken(
                token=usable, expires_at=_as_utc(row.expires_at) or now
            )
            return "", usable

        if not row.refresh_token:
            raise ZaloTokenMissing(
                f"zalo_oa_credentials row for app_id={app_id} has no "
                "refresh_token; the OA must be re-authorised by hand. "
                f"See {RUNBOOK}"
            )

        # Everything the HTTP call needs must be validated *before* the
        # write-ahead commit. ZALO_APP_SECRET is checked in _post_refresh
        # too (it is the header that authenticates the call), but failing
        # there would leave a durable refresh_pending marker behind for a
        # request that never left the process — and _guard_pending turns
        # that marker into a permanent, human-only stop. A missing secret
        # is a config error; it must not cost an OA re-authorisation.
        if not get_settings().zalo_app_secret:
            raise ZaloTokenMissing(
                "ZALO_APP_SECRET is not configured — refusing to start a "
                f"refresh for app_id={app_id} that cannot be authenticated."
            )

        # 3 — write-ahead. This COMMIT is the whole point of the protocol:
        # after it, a crash is diagnosable instead of silent.
        row.refresh_pending_token = row.refresh_token
        row.refresh_pending_at = now
        await db.commit()

        logger.info("zalo.token.refresh start app_id=%s force=%s", app_id, force)
        return row.refresh_token, None


def _guard_pending(app_id: str, row: ZaloOACredential) -> None:
    """Refuse to touch a credential that is already mid-refresh."""
    if not row.refresh_pending_token:
        return

    pending_at = _as_utc(row.refresh_pending_at)
    age = _now() - pending_at if pending_at is not None else IN_FLIGHT_GRACE
    if age < IN_FLIGHT_GRACE:
        # Someone else is between steps 3 and 5. Not an error — back off.
        raise ZaloTokenRefreshInFlight(
            f"A refresh for app_id={app_id} started "
            f"{age.total_seconds():.1f}s ago is still running."
        )

    # Older than the grace period: a process died mid-refresh. We cannot
    # know whether Zalo consumed the token, and guessing wrong costs a
    # manual OA re-authorisation, so this stops here — permanently — until
    # a human works the runbook.
    logger.critical(
        "zalo.token.refresh_pending app_id=%s age_seconds=%.0f — a refresh "
        "died between the write-ahead commit and the result commit. NOT "
        "retrying: the pending refresh_token may already have been consumed "
        "by Zalo. Work the runbook: %s",
        app_id,
        age.total_seconds(),
        RUNBOOK,
    )
    raise ZaloTokenRefreshStuck(
        f"zalo_oa_credentials.refresh_pending_token is set for "
        f"app_id={app_id}; manual recovery required. See {RUNBOOK}"
    )


def _token_already_usable(
    row: ZaloOACredential,
    *,
    force: bool,
    stale_token: str | None,
    now: datetime,
) -> str | None:
    """Decide whether the stored token spares us the HTTP call."""
    if not row.access_token:
        return None
    if force:
        # Only skip a forced refresh when the stored token has actually
        # rotated away from the one that failed. Without a stale_token to
        # compare against we have to assume the stored token is the bad one.
        if stale_token and row.access_token != stale_token:
            return row.access_token
        return None
    if _is_fresh(row.expires_at, now=now):
        return row.access_token
    return None


async def _post_refresh(app_id: str, refresh_token: str) -> dict:
    """Step 4 — exactly one attempt. See the module docstring."""
    settings = get_settings()
    if not settings.zalo_app_secret:
        raise ZaloTokenMissing(
            "ZALO_APP_SECRET is not configured — the refresh call cannot "
            "be authenticated."
        )

    client = await _get_http_client()
    try:
        response = await client.post(
            REFRESH_URL,
            headers={
                "secret_key": settings.zalo_app_secret,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "app_id": app_id,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )
    except Exception as exc:  # network error, timeout, DNS…
        # refresh_pending stays set on purpose: the request may have
        # reached Zalo and rotated the token even though we never saw a
        # response. _guard_pending turns this into the runbook.
        logger.critical(
            "zalo.token.refresh transport_error app_id=%s error=%s — the "
            "refresh_token may or may not have been consumed; not retrying. "
            "Runbook: %s",
            app_id,
            type(exc).__name__,
            RUNBOOK,
        )
        raise ZaloTokenRefreshFailed(
            f"Refresh request for app_id={app_id} failed in transport."
        ) from exc

    body = _parse_json_safe(response)
    error_code = body.get("error", 0)
    access_token = body.get("access_token")

    if response.status_code != 200 or error_code or not access_token:
        logger.critical(
            "zalo.token.refresh rejected app_id=%s http=%s error=%s name=%s "
            "— refresh_pending left set for diagnosis. Runbook: %s",
            app_id,
            response.status_code,
            error_code,
            body.get("error_name") or body.get("error_description"),
            RUNBOOK,
        )
        raise ZaloTokenRefreshFailed(
            f"Zalo rejected the refresh for app_id={app_id} "
            f"(http={response.status_code}, error={error_code})."
        )

    return body


async def _finish_refresh(app_id: str, payload: dict) -> str:
    """Step 5 — persist the rotated pair and clear the pending marker."""
    access_token = str(payload["access_token"])
    # Zalo returns expires_in as a string; a rotated refresh_token should
    # always be present, but never overwrite a good one with an empty one.
    new_refresh = payload.get("refresh_token")
    expires_in = _coerce_expires_in(payload.get("expires_in"))
    now = _now()
    expires_at = now + timedelta(seconds=expires_in)

    factory = get_session_factory()
    async with factory() as db:
        await _acquire_advisory_lock(db, app_id)
        row = await db.get(ZaloOACredential, app_id)
        if row is None:  # pragma: no cover - the row existed one step ago
            raise ZaloTokenMissing(
                f"zalo_oa_credentials row for app_id={app_id} vanished "
                "mid-refresh."
            )

        row.access_token = access_token
        if new_refresh:
            row.refresh_token = str(new_refresh)
        else:
            logger.error(
                "zalo.token.refresh app_id=%s returned no refresh_token — "
                "keeping the previous one, which Zalo has probably already "
                "invalidated. Expect the next refresh to fail.",
                app_id,
            )
        row.expires_at = expires_at
        row.refresh_pending_token = None
        row.refresh_pending_at = None
        row.refresh_count = (row.refresh_count or 0) + 1
        row.last_refreshed_at = now
        await db.commit()

    _cache[app_id] = _CachedToken(token=access_token, expires_at=expires_at)
    logger.info(
        "zalo.token.refresh ok app_id=%s expires_in=%s rotated=%s",
        app_id,
        expires_in,
        bool(new_refresh),
    )
    return access_token


def _coerce_expires_in(value: object) -> int:
    """Zalo sends ``"3600"``. Fall back to one hour on anything odd."""
    try:
        seconds = int(str(value))
    except (TypeError, ValueError):
        seconds = 0
    if seconds <= 0:
        logger.warning(
            "zalo.token.refresh unusable expires_in=%r — assuming 3600s", value
        )
        seconds = 3600
    return seconds


def _parse_json_safe(response: httpx.Response) -> dict:
    try:
        body = response.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}
