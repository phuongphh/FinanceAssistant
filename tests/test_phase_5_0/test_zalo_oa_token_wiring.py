"""Phase 5.0 #1.4 — ZaloOAClient token provider + expired-token replay.

Phase 4B captured the access token once, at process start. Zalo access
tokens live one hour, so that client was guaranteed to be sending with a
dead token by the second hour of any deploy and had no way to notice.

What these tests pin:

* the token is resolved **per send**, not per construction;
* a token-expired app error triggers exactly one forced refresh and one
  replay — never a loop, never two refreshes (each refresh burns a
  single-use ``refresh_token``);
* the replay does **not** spend a 429 backoff slot, so a send that races
  the hourly rotation keeps the same retry budget as one that doesn't;
* the static Phase 4B token still works untouched when nothing is wired,
  which is what keeps ``ZALO_CHANNEL_ENABLED=false`` byte-identical to
  pre-5.0 behaviour.

Transport is ``httpx.MockTransport`` (same pattern as
``tests/test_phase_4b/test_epic4_zalo.py``) and every request's headers
are captured, because "did the replay actually use the new token?" is the
question the whole story hangs on.
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from backend.adapters import zalo_oa

STATIC = "static-4b-token"
FRESH = "fresh-token"


# ---------------------------------------------------------------------------
# Scaffolding
# ---------------------------------------------------------------------------


class _Transport:
    """Serves canned responses FIFO and records the token on each request."""

    def __init__(self, responses: list[httpx.Response]):
        self._responses = responses
        self.tokens: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.tokens.append(request.headers.get("access_token", ""))
        idx = min(len(self.tokens) - 1, len(self._responses) - 1)
        return self._responses[idx]

    @property
    def calls(self) -> int:
        return len(self.tokens)


def _ok() -> httpx.Response:
    return httpx.Response(200, json={"error": 0, "message": "Success"})


def _app_error(code: int) -> httpx.Response:
    return httpx.Response(200, json={"error": code, "message": f"err {code}"})


class _Provider:
    """Async token provider that counts calls."""

    def __init__(self, *tokens: str):
        self._tokens = list(tokens) or [""]
        self.calls = 0

    async def __call__(self) -> str:
        self.calls += 1
        idx = min(self.calls - 1, len(self._tokens) - 1)
        return self._tokens[idx]


class _Refresher:
    """Async refresher that records the stale token it was handed."""

    def __init__(self, result: str = FRESH, raises: Exception | None = None):
        self._result = result
        self._raises = raises
        self.stale_tokens: list[str] = []

    async def __call__(self, stale: str) -> str:
        self.stale_tokens.append(stale)
        if self._raises is not None:
            raise self._raises
        return self._result

    @property
    def calls(self) -> int:
        return len(self.stale_tokens)


@pytest.fixture
def wire(monkeypatch):
    """Install a mock transport and neutralise backoff sleeps."""
    sleeps: list[float] = []

    async def _sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(zalo_oa.asyncio, "sleep", _sleep)

    def _install(responses: list[httpx.Response]) -> _Transport:
        transport = _Transport(responses)
        client = httpx.AsyncClient(transport=httpx.MockTransport(transport.handler))

        async def _fake_get_client() -> httpx.AsyncClient:
            return client

        monkeypatch.setattr(zalo_oa, "_get_client", _fake_get_client)
        return transport

    _install.sleeps = sleeps  # type: ignore[attr-defined]
    return _install


# ---------------------------------------------------------------------------
# Static token — Phase 4B behaviour must survive untouched
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_static_token_is_sent_when_no_provider_is_wired(wire):
    transport = wire([_ok()])

    client = zalo_oa.ZaloOAClient(access_token=STATIC)
    assert await client.send_message("u", "hi") is True
    assert transport.tokens == [STATIC]


def test_is_configured_is_false_with_neither_token_nor_provider():
    assert zalo_oa.ZaloOAClient().is_configured is False
    assert zalo_oa.ZaloOAClient(access_token="").is_configured is False


def test_is_configured_is_true_with_only_a_provider():
    """A provider counts as configured even with no static token.

    ``is_configured`` is a synchronous pre-flight check; asking the
    provider for real would mean a DB round trip inside a property.
    """
    client = zalo_oa.ZaloOAClient(token_provider=_Provider("t"))
    assert client.is_configured is True


@pytest.mark.asyncio
async def test_expired_code_without_a_refresher_fails_once(wire):
    """A 4B-style static client has nothing to refresh with — no replay."""
    transport = wire([_app_error(-216)])

    client = zalo_oa.ZaloOAClient(access_token=STATIC)
    assert await client.send_message("u", "hi") is False
    assert transport.calls == 1


# ---------------------------------------------------------------------------
# Provider path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_token_is_resolved_per_send_not_per_construction(wire):
    """The whole point of #1.4: hour two of a deploy must not send a dead
    token. Two sends ⇒ two provider calls, second one's token on the wire."""
    transport = wire([_ok(), _ok()])
    provider = _Provider("token-hour-1", "token-hour-2")

    client = zalo_oa.ZaloOAClient(token_provider=provider)
    assert await client.send_message("u", "one") is True
    assert await client.send_message("u", "two") is True

    assert provider.calls == 2
    assert transport.tokens == ["token-hour-1", "token-hour-2"]


@pytest.mark.asyncio
async def test_empty_provider_answer_short_circuits_before_any_http(wire):
    """The provider is authoritative. It already decided the static token
    does not apply, so we must not resurrect it behind its back."""
    transport = wire([_ok()])
    provider = _Provider("")

    client = zalo_oa.ZaloOAClient(access_token=STATIC, token_provider=provider)
    assert await client.send_message("u", "hi") is False
    assert transport.calls == 0


@pytest.mark.asyncio
async def test_provider_exception_falls_back_to_the_static_token(wire):
    """Defensive only — the wired provider swallows its own errors. But a
    Notifier must never see an exception from a send."""
    transport = wire([_ok()])

    async def boom() -> str:
        raise RuntimeError("provider is broken")

    client = zalo_oa.ZaloOAClient(access_token=STATIC, token_provider=boom)
    assert await client.send_message("u", "hi") is True
    assert transport.tokens == [STATIC]


@pytest.mark.asyncio
async def test_provider_exception_without_static_token_fails_open(wire):
    transport = wire([_ok()])

    async def boom() -> str:
        raise RuntimeError("provider is broken")

    client = zalo_oa.ZaloOAClient(token_provider=boom)
    assert await client.send_message("u", "hi") is False
    assert transport.calls == 0


@pytest.mark.asyncio
async def test_image_send_also_resolves_a_token(wire):
    """``send_image_message`` shares ``_post``; pin it so a future edit
    can't leave one of the two send paths on a stale token."""
    transport = wire([_ok()])
    provider = _Provider("img-token")

    client = zalo_oa.ZaloOAClient(token_provider=provider)
    ok = await client.send_image_message("u", "https://example.com/a.png", "cap")
    assert ok is True
    assert transport.tokens == ["img-token"]


# ---------------------------------------------------------------------------
# Token-expired replay
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("code", [-216, -201])
@pytest.mark.asyncio
async def test_expired_token_is_refreshed_and_the_send_replayed(wire, code):
    transport = wire([_app_error(code), _ok()])
    provider = _Provider("stale-token")
    refresher = _Refresher(FRESH)

    client = zalo_oa.ZaloOAClient(token_provider=provider, token_refresher=refresher)
    assert await client.send_message("u", "hi") is True

    assert transport.tokens == ["stale-token", FRESH]
    # The refresher is told which token failed so a refresh another
    # coroutine already did can be reused instead of burning a second
    # single-use refresh_token.
    assert refresher.stale_tokens == ["stale-token"]
    # One send, one provider call — the replay reuses the refresh result.
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_only_one_refresh_per_send(wire):
    """Second rejection after a successful refresh is a real problem
    (revoked OA, wrong app). Retrying it would hammer Zalo forever."""
    transport = wire([_app_error(-216), _app_error(-216), _ok()])
    refresher = _Refresher(FRESH)

    client = zalo_oa.ZaloOAClient(
        token_provider=_Provider("stale-token"), token_refresher=refresher
    )
    # Zalo answered — twice, with a token it says is bad. The quota slot
    # may already be spent, so this is a rejection, not a fail-open.
    with pytest.raises(zalo_oa.ZaloSendRejected):
        await client.send_message("u", "hi")
    assert transport.calls == 2
    assert refresher.calls == 1


@pytest.mark.asyncio
async def test_failed_refresh_gives_up_without_replaying(wire):
    transport = wire([_app_error(-216), _ok()])
    refresher = _Refresher("")

    client = zalo_oa.ZaloOAClient(
        token_provider=_Provider("stale-token"), token_refresher=refresher
    )
    assert await client.send_message("u", "hi") is False
    assert transport.calls == 1


@pytest.mark.asyncio
async def test_refresh_returning_the_same_token_does_not_replay(wire):
    """A no-op refresh would make the replay fail identically. Stop."""
    transport = wire([_app_error(-216), _ok()])
    refresher = _Refresher("stale-token")

    client = zalo_oa.ZaloOAClient(
        token_provider=_Provider("stale-token"), token_refresher=refresher
    )
    assert await client.send_message("u", "hi") is False
    assert transport.calls == 1


@pytest.mark.asyncio
async def test_refresher_exception_fails_open(wire):
    transport = wire([_app_error(-216), _ok()])
    refresher = _Refresher(raises=RuntimeError("refresh exploded"))

    client = zalo_oa.ZaloOAClient(
        token_provider=_Provider("stale-token"), token_refresher=refresher
    )
    assert await client.send_message("u", "hi") is False
    assert transport.calls == 1


@pytest.mark.asyncio
async def test_replay_does_not_spend_a_backoff_slot(wire):
    """A stale token is not congestion.

    Sequence: token-expired, then 429 forever. The send must still get its
    full 1 initial + 3 backed-off attempts *after* the replay, i.e. 5
    requests total — otherwise a send that happens to race the hourly
    rotation is quietly less resilient than one that doesn't.
    """
    transport = wire(
        [
            _app_error(-216),
            httpx.Response(429, json={"error": "rate"}),
        ]
    )
    client = zalo_oa.ZaloOAClient(
        token_provider=_Provider("stale-token"), token_refresher=_Refresher(FRESH)
    )
    with pytest.raises(zalo_oa.ZaloSendRejected):
        await client.send_message("u", "hi")

    assert transport.calls == 5
    assert transport.tokens[0] == "stale-token"
    assert transport.tokens[1:] == [FRESH] * 4
    assert wire.sleeps == list(zalo_oa._RETRY_BACKOFFS_SECONDS)


@pytest.mark.asyncio
async def test_transient_app_codes_still_ride_the_backoff_schedule(wire):
    """Regression guard for the loop rewrite: -32/-239 kept their retries."""
    transport = wire([_app_error(-32), _app_error(-32), _ok()])

    client = zalo_oa.ZaloOAClient(access_token=STATIC)
    assert await client.send_message("u", "hi") is True
    assert transport.calls == 3
    assert wire.sleeps == [2.0, 4.0]


@pytest.mark.asyncio
async def test_transient_app_codes_give_up_after_three_retries(wire):
    transport = wire([_app_error(-239)])

    client = zalo_oa.ZaloOAClient(access_token=STATIC)
    with pytest.raises(zalo_oa.ZaloSendRejected):
        await client.send_message("u", "hi")
    assert transport.calls == 4


# ---------------------------------------------------------------------------
# Composition root — _make_token_callables / get_zalo_oa_client
# ---------------------------------------------------------------------------


def _settings(**overrides) -> SimpleNamespace:
    base = {
        "zalo_channel_enabled": True,
        "zalo_app_id": "app-1234",
        "zalo_oa_access_token": STATIC,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_credentials_survive_the_channel_flag():
    """The flag governs *sending*, not credential resolution.

    ``/admin/zalo-quota`` is mounted unconditionally so an operator can
    read the OA's allowance before a rollout and — more importantly —
    after a rollback. If the provider vanished with the flag, those
    endpoints would report "unavailable" at exactly the moment the
    runbook says to use them.
    """
    provider, refresher = zalo_oa._make_token_callables(
        _settings(zalo_channel_enabled=False)
    )
    assert provider is not None and refresher is not None


def test_send_is_disabled_when_the_channel_is_off(monkeypatch):
    """The gate that *did* move: sending, checked at the emitting edges."""
    monkeypatch.setattr(
        zalo_oa, "get_settings", lambda: _settings(zalo_channel_enabled=False)
    )
    assert zalo_oa.ZaloOAClient(access_token=STATIC).is_send_enabled is False

    monkeypatch.setattr(zalo_oa, "get_settings", _settings)
    assert zalo_oa.ZaloOAClient(access_token=STATIC).is_send_enabled is True


def test_no_callables_without_an_app_id():
    """No app id means the token service cannot identify the OA row; the
    static token is the only thing that can work."""
    provider, refresher = zalo_oa._make_token_callables(_settings(zalo_app_id=""))
    assert provider is None and refresher is None


@pytest.mark.asyncio
async def test_wired_provider_returns_the_service_token(monkeypatch):
    from backend.services import zalo_token_service as token_service

    async def fake_get_access_token(app_id=None) -> str:
        return "db-token"

    monkeypatch.setattr(token_service, "get_access_token", fake_get_access_token)

    provider, _ = zalo_oa._make_token_callables(_settings())
    assert await provider() == "db-token"


@pytest.mark.asyncio
async def test_wired_provider_falls_back_to_static_when_nothing_is_seeded(
    monkeypatch,
):
    """``ZaloTokenMissing`` is the documented static-fallback case: no
    credential row yet. Everything else is a live incident, not a fallback."""
    from backend.services import zalo_token_service as token_service

    async def missing(app_id=None) -> str:
        raise token_service.ZaloTokenMissing("no row")

    monkeypatch.setattr(token_service, "get_access_token", missing)

    provider, _ = zalo_oa._make_token_callables(_settings())
    assert await provider() == STATIC


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc_name",
    ["ZaloTokenRefreshInFlight", "ZaloTokenRefreshStuck", "ZaloTokenRefreshFailed"],
)
async def test_wired_provider_yields_nothing_on_a_live_token_incident(
    monkeypatch, exc_name
):
    """A stuck/failed refresh means the stored token is in an unknown
    state. The 4B static token is from a different era and would only buy
    an opaque platform error, so the send is dropped instead."""
    from backend.services import zalo_token_service as token_service

    exc_class = getattr(token_service, exc_name)

    async def boom(app_id=None) -> str:
        raise exc_class("nope")

    monkeypatch.setattr(token_service, "get_access_token", boom)

    provider, _ = zalo_oa._make_token_callables(_settings())
    assert await provider() == ""


@pytest.mark.asyncio
async def test_wired_refresher_forwards_the_stale_token(monkeypatch):
    from backend.services import zalo_token_service as token_service

    seen: dict[str, str] = {}

    async def fake_force_refresh(app_id=None, *, stale_token="") -> str:
        seen["stale"] = stale_token
        return FRESH

    monkeypatch.setattr(token_service, "force_refresh", fake_force_refresh)

    _, refresher = zalo_oa._make_token_callables(_settings())
    assert await refresher("old-token") == FRESH
    assert seen["stale"] == "old-token"


@pytest.mark.asyncio
async def test_wired_refresher_swallows_token_errors(monkeypatch):
    from backend.services import zalo_token_service as token_service

    async def boom(app_id=None, *, stale_token="") -> str:
        raise token_service.ZaloTokenRefreshFailed("nope")

    monkeypatch.setattr(token_service, "force_refresh", boom)

    _, refresher = zalo_oa._make_token_callables(_settings())
    assert await refresher("old-token") == ""


def test_factory_wires_the_provider_when_the_channel_is_on(monkeypatch):
    monkeypatch.setattr(zalo_oa, "get_settings", lambda: _settings())
    zalo_oa._reset_for_tests()
    try:
        client = zalo_oa.get_zalo_oa_client()
        assert client._token_provider is not None
        assert client._token_refresher is not None
        assert client.is_configured is True
    finally:
        zalo_oa._reset_for_tests()


def test_factory_keeps_the_static_token_as_a_fallback_when_the_channel_is_off(
    monkeypatch,
):
    """Flag off still yields a *readable* client, just not a sending one.

    The DB-backed provider stays wired (admin diagnostics), the legacy
    static token stays as its fallback, and ``is_send_enabled`` is the
    single thing that goes false.
    """
    monkeypatch.setattr(
        zalo_oa, "get_settings", lambda: _settings(zalo_channel_enabled=False)
    )
    zalo_oa._reset_for_tests()
    try:
        client = zalo_oa.get_zalo_oa_client()
        assert client._token_provider is not None
        assert client._token_refresher is not None
        assert client._static_token == STATIC
        assert client.is_send_enabled is False
    finally:
        zalo_oa._reset_for_tests()
