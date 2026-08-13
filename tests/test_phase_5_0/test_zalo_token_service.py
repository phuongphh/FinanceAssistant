"""Phase 5.0 #1.3 — Zalo OA token lifecycle.

The refresh token is **single-use**: Zalo invalidates the old one the
instant the refresh HTTP call succeeds, and losing it costs a manual OA
re-authorisation. So the properties pinned here are mostly about what the
service refuses to do:

* it never issues two refreshes where one would do (concurrency, cache);
* it never retries the refresh POST — a retry can burn a token whose first
  attempt succeeded but whose response was lost;
* it never blind-retries a ``refresh_pending`` row left behind by a crash;
* it never logs or returns token material it does not have to.

The DB is faked rather than sqlite-backed on purpose: ``aiosqlite`` is not
in the test environment, and the fake also lets us assert the *ordering* of
lock / commit / HTTP, which is the actual invariant of the write-ahead
protocol. A real session would hide that behind SQL.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("sqlalchemy")

# noqa: E402 below — imports must follow the importorskip guard above.
from backend.models.zalo_oa_credential import ZaloOACredential  # noqa: E402
from backend.services import zalo_token_service as svc  # noqa: E402

APP_ID = "app-1234"
ACCESS = "access-token-old"
REFRESH = "refresh-token-old"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Fake DB
# ---------------------------------------------------------------------------


class _FakeSession:
    """Enough AsyncSession for the protocol, plus an operation log."""

    def __init__(self, store: dict[str, ZaloOACredential], ops: list[str]) -> None:
        self._store = store
        self._ops = ops

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *exc_info) -> bool:
        return False

    async def execute(self, statement, params=None):
        # The only statement the service issues is pg_advisory_xact_lock.
        self._ops.append("lock")
        return None

    async def get(self, model, pk):
        return self._store.get(pk)

    def add(self, row) -> None:  # pragma: no cover - unused by the service
        self._store[row.app_id] = row

    async def commit(self) -> None:
        row = self._store.get(APP_ID)
        pending = bool(row and row.refresh_pending_token)
        self._ops.append("commit:pending" if pending else "commit:final")


class _FakeFactory:
    def __init__(self, store: dict[str, ZaloOACredential], ops: list[str]) -> None:
        self.store = store
        self.ops = ops
        self.sessions_opened = 0

    def __call__(self) -> _FakeSession:
        self.sessions_opened += 1
        return _FakeSession(self.store, self.ops)


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class _FakeHTTPClient:
    """Records refresh calls; optionally fails."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.response = _FakeResponse(
            {
                "access_token": "access-token-new",
                "refresh_token": "refresh-token-new",
                "expires_in": "3600",
            }
        )
        self.raises: Exception | None = None
        self.delay = 0.0

    async def post(self, url, *, headers=None, data=None):
        self.calls.append({"url": url, "headers": headers or {}, "data": data or {}})
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.raises is not None:
            raise self.raises
        return self.response


def _credential(**overrides) -> ZaloOACredential:
    row = ZaloOACredential(app_id=APP_ID)
    row.access_token = overrides.pop("access_token", ACCESS)
    row.refresh_token = overrides.pop("refresh_token", REFRESH)
    row.expires_at = overrides.pop("expires_at", _utcnow() + timedelta(hours=1))
    row.refresh_pending_token = overrides.pop("refresh_pending_token", None)
    row.refresh_pending_at = overrides.pop("refresh_pending_at", None)
    row.refresh_count = overrides.pop("refresh_count", 0)
    row.last_refreshed_at = overrides.pop("last_refreshed_at", None)
    assert not overrides, f"unknown overrides: {overrides}"
    return row


@pytest.fixture()
def env(monkeypatch):
    """Wire the service to a fake DB + fake HTTP client."""
    svc.reset_cache_for_tests()

    store: dict[str, ZaloOACredential] = {}
    ops: list[str] = []
    factory = _FakeFactory(store, ops)
    http = _FakeHTTPClient()

    monkeypatch.setattr(svc, "get_session_factory", lambda: factory)

    async def _client():
        return http

    monkeypatch.setattr(svc, "_get_http_client", _client)

    settings = svc.get_settings()
    monkeypatch.setattr(settings, "zalo_app_id", APP_ID)
    monkeypatch.setattr(settings, "zalo_app_secret", "app-secret")

    class _Env:
        pass

    e = _Env()
    e.store = store
    e.ops = ops
    e.factory = factory
    e.http = http
    e.settings = settings
    try:
        yield e
    finally:
        svc.reset_cache_for_tests()


def _seed(env, **overrides) -> ZaloOACredential:
    row = _credential(**overrides)
    env.store[APP_ID] = row
    return row


# ---------------------------------------------------------------------------
# Happy path / freshness
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fresh_token_is_returned_without_refreshing(env):
    _seed(env, expires_at=_utcnow() + timedelta(minutes=59))

    assert await svc.get_access_token() == ACCESS
    assert env.http.calls == []


@pytest.mark.asyncio
async def test_expired_token_triggers_refresh(env):
    _seed(env, expires_at=_utcnow() - timedelta(minutes=1))

    assert await svc.get_access_token() == "access-token-new"
    assert len(env.http.calls) == 1


@pytest.mark.asyncio
async def test_write_ahead_ordering(env):
    """lock → COMMIT(pending) → HTTP → lock → COMMIT(final).

    The pending marker must be durable *before* the call goes out; if the
    commit moved after the POST a crash would leave no trace that a token
    had been consumed.
    """
    _seed(env, expires_at=_utcnow() - timedelta(minutes=1))

    def _mark_http(*a, **kw):
        env.ops.append("http")

    original_post = env.http.post

    async def _post(url, *, headers=None, data=None):
        _mark_http()
        return await original_post(url, headers=headers, data=data)

    env.http.post = _post

    await svc.get_access_token()

    assert env.ops == ["lock", "commit:pending", "http", "lock", "commit:final"]


@pytest.mark.asyncio
async def test_refresh_persists_rotated_pair_and_clears_pending(env):
    row = _seed(env, expires_at=_utcnow() - timedelta(minutes=1))

    await svc.get_access_token()

    assert row.access_token == "access-token-new"
    assert row.refresh_token == "refresh-token-new"
    assert row.refresh_pending_token is None
    assert row.refresh_pending_at is None
    assert row.refresh_count == 1
    assert row.last_refreshed_at is not None
    assert row.expires_at > _utcnow() + timedelta(minutes=50)


@pytest.mark.asyncio
async def test_refresh_request_shape(env):
    """The refresh uses the OAuth host, the secret_key header and a form body."""
    _seed(env, expires_at=_utcnow() - timedelta(minutes=1))

    await svc.get_access_token()

    call = env.http.calls[0]
    assert call["url"] == svc.REFRESH_URL
    assert call["headers"]["secret_key"] == "app-secret"
    assert call["data"] == {
        "app_id": APP_ID,
        "grant_type": "refresh_token",
        "refresh_token": REFRESH,
    }
    # The refresh token must never travel as a bearer/access header.
    assert "access_token" not in call["headers"]


# ---------------------------------------------------------------------------
# Skew / expiry edges
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_token_inside_the_skew_window_is_refreshed_early(env):
    """A token with 4 minutes left must not be handed to a new send."""
    _seed(env, expires_at=_utcnow() + timedelta(minutes=4))

    assert await svc.get_access_token() == "access-token-new"


@pytest.mark.asyncio
async def test_token_just_outside_the_skew_window_is_kept(env):
    _seed(env, expires_at=_utcnow() + timedelta(minutes=6))

    assert await svc.get_access_token() == ACCESS
    assert env.http.calls == []


@pytest.mark.asyncio
async def test_null_expires_at_is_treated_as_expired(env):
    """Unknown expiry must not be optimistically trusted."""
    _seed(env, expires_at=None)

    assert await svc.get_access_token() == "access-token-new"


@pytest.mark.asyncio
async def test_naive_expires_at_is_interpreted_as_utc(env):
    """A hand-seeded naive timestamp must not raise on comparison."""
    _seed(env, expires_at=datetime.utcnow() + timedelta(minutes=59))

    assert await svc.get_access_token() == ACCESS
    assert env.http.calls == []


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_two_concurrent_callers_trigger_exactly_one_refresh(env):
    """The single-use refresh token makes a double refresh destructive."""
    _seed(env, expires_at=_utcnow() - timedelta(minutes=1))
    env.http.delay = 0.02

    tokens = await asyncio.gather(
        svc.get_access_token(), svc.get_access_token(), svc.get_access_token()
    )

    assert tokens == ["access-token-new"] * 3
    assert len(env.http.calls) == 1


@pytest.mark.asyncio
async def test_cached_token_avoids_a_second_db_round_trip(env):
    """Every outbound message needs a token; it must not cost a query."""
    _seed(env, expires_at=_utcnow() - timedelta(minutes=1))

    await svc.get_access_token()
    opened_after_refresh = env.factory.sessions_opened

    await svc.get_access_token()
    await svc.get_access_token()

    assert env.factory.sessions_opened == opened_after_refresh


# ---------------------------------------------------------------------------
# refresh_pending — the crash path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recent_pending_marker_is_reported_as_in_flight(env):
    """Another process is mid-refresh — transient, not a page."""
    _seed(
        env,
        expires_at=_utcnow() - timedelta(minutes=1),
        refresh_pending_token=REFRESH,
        refresh_pending_at=_utcnow() - timedelta(seconds=5),
    )

    with pytest.raises(svc.ZaloTokenRefreshInFlight):
        await svc.get_access_token()

    assert env.http.calls == []


@pytest.mark.asyncio
async def test_stale_pending_marker_is_never_blind_retried(env, caplog):
    """A crashed refresh must stop the line, loudly, until a human looks.

    Retrying here is the one move that can cost a manual OA
    re-authorisation, because we cannot know whether Zalo already consumed
    the pending refresh_token.
    """
    _seed(
        env,
        expires_at=_utcnow() - timedelta(minutes=1),
        refresh_pending_token=REFRESH,
        refresh_pending_at=_utcnow() - svc.IN_FLIGHT_GRACE - timedelta(seconds=1),
    )

    with caplog.at_level(logging.CRITICAL):
        with pytest.raises(svc.ZaloTokenRefreshStuck):
            await svc.get_access_token()

    assert env.http.calls == []
    blob = "\n".join(r.getMessage() for r in caplog.records)
    assert "zalo.token.refresh_pending" in blob
    assert svc.RUNBOOK in blob
    # The alert must not carry the token it is complaining about.
    assert REFRESH not in blob


@pytest.mark.asyncio
async def test_pending_marker_without_timestamp_is_treated_as_stuck(env):
    """A NULL attempted_at cannot be aged, so assume the worst."""
    _seed(
        env,
        expires_at=_utcnow() - timedelta(minutes=1),
        refresh_pending_token=REFRESH,
        refresh_pending_at=None,
    )

    with pytest.raises(svc.ZaloTokenRefreshStuck):
        await svc.get_access_token()


@pytest.mark.asyncio
async def test_pending_marker_does_not_block_a_still_valid_token(env):
    """A stuck refresh should not take down sends that need no refresh...

    ...but it must not be silently ignored either: the guard runs first, so
    a pending marker fails fast even when the cached token is still good.
    This test documents that deliberate choice.
    """
    _seed(
        env,
        expires_at=_utcnow() + timedelta(minutes=59),
        refresh_pending_token=REFRESH,
        refresh_pending_at=_utcnow() - timedelta(hours=2),
    )

    # Cache miss → the guard is reached → raises rather than serving a token
    # from a credential row that is in an unknown state.
    with pytest.raises(svc.ZaloTokenRefreshStuck):
        await svc.get_access_token()


# ---------------------------------------------------------------------------
# Failure of the refresh call itself
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transport_failure_is_not_retried_and_leaves_pending_set(env, caplog):
    row = _seed(env, expires_at=_utcnow() - timedelta(minutes=1))
    env.http.raises = TimeoutError("boom")

    with caplog.at_level(logging.CRITICAL):
        with pytest.raises(svc.ZaloTokenRefreshFailed):
            await svc.get_access_token()

    assert len(env.http.calls) == 1, "the refresh POST must never be retried"
    assert row.refresh_pending_token == REFRESH
    blob = "\n".join(r.getMessage() for r in caplog.records)
    assert "transport_error" in blob
    assert svc.RUNBOOK in blob


@pytest.mark.asyncio
async def test_application_level_rejection_is_a_failure(env):
    """Zalo returns app errors as HTTP 200 with a non-zero ``error``."""
    _seed(env, expires_at=_utcnow() - timedelta(minutes=1))
    env.http.response = _FakeResponse(
        {"error": -14002, "error_name": "invalid_refresh_token"}
    )

    with pytest.raises(svc.ZaloTokenRefreshFailed):
        await svc.get_access_token()


@pytest.mark.asyncio
async def test_http_error_status_is_a_failure(env):
    _seed(env, expires_at=_utcnow() - timedelta(minutes=1))
    env.http.response = _FakeResponse({"access_token": "x"}, status_code=500)

    with pytest.raises(svc.ZaloTokenRefreshFailed):
        await svc.get_access_token()


@pytest.mark.asyncio
async def test_response_without_access_token_is_a_failure(env):
    _seed(env, expires_at=_utcnow() - timedelta(minutes=1))
    env.http.response = _FakeResponse({"error": 0, "refresh_token": "r"})

    with pytest.raises(svc.ZaloTokenRefreshFailed):
        await svc.get_access_token()


@pytest.mark.asyncio
async def test_failed_refresh_leaves_the_cache_empty(env):
    """A failure must not poison later calls with a half-updated cache."""
    _seed(env, expires_at=_utcnow() - timedelta(minutes=1))
    env.http.raises = TimeoutError("boom")

    with pytest.raises(svc.ZaloTokenRefreshFailed):
        await svc.get_access_token()

    assert svc._cache == {}


# ---------------------------------------------------------------------------
# Malformed / partial responses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expires_in_is_accepted_as_a_string(env):
    row = _seed(env, expires_at=_utcnow() - timedelta(minutes=1))
    env.http.response = _FakeResponse(
        {"access_token": "a", "refresh_token": "r", "expires_in": "90000"}
    )

    await svc.get_access_token()

    assert row.expires_at > _utcnow() + timedelta(hours=24)


@pytest.mark.asyncio
async def test_unusable_expires_in_falls_back_to_one_hour(env):
    row = _seed(env, expires_at=_utcnow() - timedelta(minutes=1))
    env.http.response = _FakeResponse(
        {"access_token": "a", "refresh_token": "r", "expires_in": "nonsense"}
    )

    await svc.get_access_token()

    assert timedelta(minutes=55) < row.expires_at - _utcnow() <= timedelta(hours=1)


@pytest.mark.asyncio
async def test_missing_rotated_refresh_token_keeps_the_old_one_and_warns(env, caplog):
    row = _seed(env, expires_at=_utcnow() - timedelta(minutes=1))
    env.http.response = _FakeResponse({"access_token": "a", "expires_in": "3600"})

    with caplog.at_level(logging.ERROR):
        await svc.get_access_token()

    assert row.refresh_token == REFRESH
    assert row.refresh_pending_token is None
    blob = "\n".join(r.getMessage() for r in caplog.records)
    assert "returned no refresh_token" in blob


# ---------------------------------------------------------------------------
# force_refresh
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_force_refresh_ignores_a_still_valid_expiry(env):
    """Zalo's -216 beats our own bookkeeping."""
    _seed(env, expires_at=_utcnow() + timedelta(minutes=59))

    assert await svc.force_refresh(stale_token=ACCESS) == "access-token-new"
    assert len(env.http.calls) == 1


@pytest.mark.asyncio
async def test_force_refresh_short_circuits_when_another_caller_rotated(env):
    """N concurrent sends all get -216; only the first may spend a refresh."""
    _seed(
        env, access_token="already-rotated", expires_at=_utcnow() + timedelta(hours=1)
    )

    assert await svc.force_refresh(stale_token=ACCESS) == "already-rotated"
    assert env.http.calls == []


@pytest.mark.asyncio
async def test_force_refresh_without_stale_token_always_refreshes(env):
    """With nothing to compare against, the stored token must be assumed bad."""
    _seed(env, expires_at=_utcnow() + timedelta(hours=1))

    assert await svc.force_refresh() == "access-token-new"
    assert len(env.http.calls) == 1


@pytest.mark.asyncio
async def test_force_refresh_drops_the_cached_token(env):
    _seed(env, expires_at=_utcnow() + timedelta(minutes=59))
    await svc.get_access_token()  # populate the cache
    assert svc._cache

    await svc.force_refresh()

    assert svc._cache[APP_ID].token == "access-token-new"


@pytest.mark.asyncio
async def test_concurrent_force_refresh_spends_one_token(env):
    _seed(env, expires_at=_utcnow() + timedelta(hours=1))
    env.http.delay = 0.02

    tokens = await asyncio.gather(
        svc.force_refresh(stale_token=ACCESS),
        svc.force_refresh(stale_token=ACCESS),
        svc.force_refresh(stale_token=ACCESS),
    )

    assert tokens == ["access-token-new"] * 3
    assert len(env.http.calls) == 1


# ---------------------------------------------------------------------------
# Missing configuration / rows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_credential_row_names_the_seed_script(env):
    with pytest.raises(svc.ZaloTokenMissing) as exc:
        await svc.get_access_token()

    assert "seed_zalo_credentials" in str(exc.value)


@pytest.mark.asyncio
async def test_missing_refresh_token_points_at_the_runbook(env):
    _seed(env, refresh_token=None, expires_at=_utcnow() - timedelta(minutes=1))

    with pytest.raises(svc.ZaloTokenMissing) as exc:
        await svc.get_access_token()

    assert svc.RUNBOOK in str(exc.value)


@pytest.mark.asyncio
async def test_missing_app_secret_fails_before_the_http_call(env, monkeypatch):
    _seed(env, expires_at=_utcnow() - timedelta(minutes=1))
    monkeypatch.setattr(env.settings, "zalo_app_secret", "")

    with pytest.raises(svc.ZaloTokenMissing):
        await svc.get_access_token()

    assert env.http.calls == []


@pytest.mark.asyncio
async def test_missing_app_secret_leaves_no_marker_behind(env, monkeypatch):
    """A config error must not cost an OA re-authorisation (#1).

    ``ZALO_APP_SECRET`` is checked in ``_post_refresh`` as well, but
    failing *there* is too late: the write-ahead marker is already durable
    by then, and ``_guard_pending`` turns a durable marker into a
    permanent, human-only stop. So the check has to sit before the commit.
    """
    row = _seed(env, expires_at=_utcnow() - timedelta(minutes=1))
    monkeypatch.setattr(env.settings, "zalo_app_secret", "")

    with pytest.raises(svc.ZaloTokenMissing) as exc:
        await svc.get_access_token()

    assert "ZALO_APP_SECRET" in str(exc.value)
    # Nothing was written: no pending commit, and the refresh token that a
    # marker would have stranded is still the one on the row.
    assert "commit:pending" not in env.ops
    assert row.refresh_pending_token is None
    assert row.refresh_pending_at is None
    assert row.refresh_token == REFRESH


@pytest.mark.asyncio
async def test_the_next_attempt_recovers_once_the_secret_is_restored(env, monkeypatch):
    """The point of leaving no marker: fixing the env is the whole fix.

    Had the first attempt committed one, this second call would raise
    ``ZaloTokenRefreshInFlight`` and then ``ZaloTokenRefreshStuck`` — with
    a correct config — until someone edited the credential row by hand.
    """
    _seed(env, expires_at=_utcnow() - timedelta(minutes=1))
    monkeypatch.setattr(env.settings, "zalo_app_secret", "")
    with pytest.raises(svc.ZaloTokenMissing):
        await svc.get_access_token()

    monkeypatch.setattr(env.settings, "zalo_app_secret", "app-secret")

    assert await svc.get_access_token() == "access-token-new"


@pytest.mark.asyncio
async def test_missing_app_id_is_rejected(env, monkeypatch):
    monkeypatch.setattr(env.settings, "zalo_app_id", "")

    with pytest.raises(svc.ZaloTokenMissing) as exc:
        await svc.get_access_token()

    assert "ZALO_APP_ID" in str(exc.value)


@pytest.mark.asyncio
async def test_every_error_is_a_zalo_token_error(env):
    """Callers can catch one class and degrade gracefully."""
    for klass in (
        svc.ZaloTokenMissing,
        svc.ZaloTokenRefreshInFlight,
        svc.ZaloTokenRefreshStuck,
        svc.ZaloTokenRefreshFailed,
    ):
        assert issubclass(klass, svc.ZaloTokenError)


# ---------------------------------------------------------------------------
# peek_credential — ops surface
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_peek_credential_reports_health_without_token_material(env):
    _seed(env, refresh_pending_token=REFRESH, refresh_pending_at=_utcnow())

    info = await svc.peek_credential()

    assert info["exists"] is True
    assert info["has_access_token"] is True
    assert info["has_refresh_token"] is True
    assert info["refresh_pending"] is True
    blob = repr(info)
    assert ACCESS not in blob
    assert REFRESH not in blob


@pytest.mark.asyncio
async def test_peek_credential_on_a_missing_row(env):
    info = await svc.peek_credential()

    assert info == {"app_id": APP_ID, "exists": False}


@pytest.mark.asyncio
async def test_peek_credential_never_refreshes(env):
    _seed(env, expires_at=_utcnow() - timedelta(hours=5))

    await svc.peek_credential()

    assert env.http.calls == []


# ---------------------------------------------------------------------------
# Advisory lock key
# ---------------------------------------------------------------------------


def test_advisory_key_is_deterministic_across_processes():
    """``hash()`` is PYTHONHASHSEED-randomised — two workers would lock
    different keys and both refresh. The key must be a digest."""
    assert svc._advisory_key(APP_ID) == svc._advisory_key(APP_ID)
    assert svc._advisory_key(APP_ID) != svc._advisory_key("app-other")
    assert svc._advisory_key(APP_ID) != hash(APP_ID)


def test_advisory_key_fits_a_postgres_bigint():
    for app_id in (APP_ID, "", "x" * 200, "1234567890"):
        key = svc._advisory_key(app_id)
        assert -(2**63) <= key < 2**63
