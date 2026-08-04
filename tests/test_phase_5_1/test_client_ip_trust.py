"""``X-Forwarded-For`` is only believed from a configured proxy peer.

The derived IP is a **rate-limit key**, and production publishes the app
port directly, so a caller that skips Caddy can reach the container on
its own. Before the trust rule, such a caller could rotate the forwarded
header and collect a fresh 60-second window per request — the limiter
kept counting, it just never counted the same caller twice.

The tests below are written around that attack rather than around the
happy path: the load-bearing assertions are the ones where a *forged*
header must change nothing.
"""

from __future__ import annotations

import logging

import pytest
from tests.test_phase_5_1.conftest import FakeMediaSession, InMemoryStorage

pytest.importorskip("fastapi")

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.config import Settings  # noqa: E402
from backend.database import get_db  # noqa: E402
from backend.routers import media as media_router  # noqa: E402
from backend.utils import client_ip as mod  # noqa: E402

PRIVATE = "10.0.0.7"  # where Caddy / the Docker bridge sit
PUBLIC = "203.0.113.9"  # a caller that reached the published port directly
DEFAULT = Settings.model_fields["trusted_proxy_cidrs"].default


# -- the trust rule itself -------------------------------------------------


@pytest.mark.parametrize(
    "peer",
    ["127.0.0.1", "::1", "10.0.0.7", "172.16.4.4", "192.168.1.10", "fd00::1"],
)
def test_default_trusts_loopback_and_private_ranges(peer):
    """The shipped default must cover where a real proxy actually runs.

    If it did not, every existing deployment would start rate-limiting
    all users against one key the moment this lands — the failure mode
    the CIDR default exists to avoid.
    """
    assert mod.is_trusted_proxy(peer, DEFAULT) is True


@pytest.mark.parametrize("peer", [PUBLIC, "8.8.8.8", "2001:db8::1"])
def test_default_does_not_trust_a_public_peer(peer):
    assert mod.is_trusted_proxy(peer, DEFAULT) is False


def test_empty_setting_trusts_nothing():
    """An operator who blanks the setting gets peer-keying everywhere,
    not an accidental trust-all."""
    assert mod.is_trusted_proxy(PRIVATE, "") is False
    assert mod.is_trusted_proxy("127.0.0.1", "   ,  ") is False


def test_unparseable_peer_is_not_trusted():
    """``TestClient`` uses the hostname ``testclient``, and a mangled
    value could come from a misbehaving transport. Neither can be placed
    inside a network, so neither may speak for anyone else."""
    assert mod.is_trusted_proxy("testclient", DEFAULT) is False
    assert mod.is_trusted_proxy("", DEFAULT) is False


def test_typo_in_one_cidr_is_skipped_not_fatal(caplog):
    """A bad entry degrades to "not trusted" — the safe direction —
    while the sound entries in the same list keep working."""
    raw = "10.0.0.0/8,not-a-cidr,192.168.0.0/16"
    with caplog.at_level(logging.WARNING, logger=mod.__name__):
        assert mod.is_trusted_proxy("10.1.2.3", raw) is True
    assert mod.is_trusted_proxy("192.168.0.4", raw) is True
    assert mod.is_trusted_proxy(PUBLIC, raw) is False
    assert "not-a-cidr" in caplog.text


# -- derivation ------------------------------------------------------------


def test_trusted_peer_speaks_for_the_original_client():
    assert mod.derive_client_ip(PRIVATE, "198.51.100.4", DEFAULT) == "198.51.100.4"


def test_trusted_peer_uses_the_left_most_hop():
    """Everything after the first hop was appended by intermediaries; the
    original client is the left-most entry."""
    header = " 198.51.100.4 , 10.0.0.7 , 10.0.0.8 "
    assert mod.derive_client_ip(PRIVATE, header, DEFAULT) == "198.51.100.4"


def test_untrusted_peer_header_is_ignored():
    """The attack, stated directly: a forged header from a public peer
    must not change the key."""
    assert mod.derive_client_ip(PUBLIC, "198.51.100.4", DEFAULT) == PUBLIC


def test_untrusted_peer_cannot_mint_distinct_keys():
    """Rotating the header per request has to collapse to one key, or
    the limiter never counts the same caller twice."""
    forged = [f"198.51.100.{n}" for n in range(1, 25)]
    keys = {mod.derive_client_ip(PUBLIC, value, DEFAULT) for value in forged}
    assert keys == {PUBLIC}


@pytest.mark.parametrize("header", [None, "", "   ", " , "])
def test_absent_or_blank_header_falls_back_to_the_peer(header):
    """Both paths must agree: a trusted proxy that sends nothing usable
    is keyed the same as one that sends no header at all."""
    assert mod.derive_client_ip(PRIVATE, header, DEFAULT) == PRIVATE


def test_no_peer_at_all_yields_the_unknown_constant():
    """An ASGI scope without a client. A string rather than ``None`` so
    callers can key a dict with it unchanged."""
    assert mod.derive_client_ip(None, None, DEFAULT) == mod.UNKNOWN_IP
    assert mod.derive_client_ip(None, "198.51.100.4", DEFAULT) == mod.UNKNOWN_IP


# -- through a real request ------------------------------------------------


def _probe_app() -> FastAPI:
    app = FastAPI()

    @app.get("/whoami")
    async def whoami(request: Request) -> dict[str, str]:
        return {"ip": mod.client_ip(request)}

    return app


@pytest.fixture()
def settings_cidrs(monkeypatch):
    """Swap the setting the helper reads.

    Patches ``backend.utils.client_ip.get_settings`` specifically: other
    modules import ``get_settings`` under their own name, and a patch
    there would not reach this one.
    """

    def _set(raw: str) -> None:
        monkeypatch.setattr(mod, "get_settings", lambda: _FakeSettings(raw))

    return _set


class _FakeSettings:
    def __init__(self, raw: str) -> None:
        self.trusted_proxy_cidrs = raw


def test_request_from_trusted_peer_is_forwarded(settings_cidrs):
    settings_cidrs(DEFAULT)
    with TestClient(_probe_app(), client=(PRIVATE, 51234)) as client:
        body = client.get("/whoami", headers={"x-forwarded-for": "198.51.100.4"}).json()
    assert body["ip"] == "198.51.100.4"


def test_request_from_untrusted_peer_is_keyed_by_its_own_address(
    settings_cidrs,
):
    settings_cidrs(DEFAULT)
    with TestClient(_probe_app(), client=(PUBLIC, 51234)) as client:
        body = client.get("/whoami", headers={"x-forwarded-for": "198.51.100.4"}).json()
    assert body["ip"] == PUBLIC


# -- what it buys the limiter ----------------------------------------------


class _MediaSettings:
    media_rate_limit_per_minute = 3
    media_storage_path = "/unused"


@pytest.fixture()
def limited(monkeypatch):
    """The media route with a ceiling of 3 and an empty store behind it.

    Every token below is unknown, so a request that gets *past* the
    limiter answers 404. That makes 404-vs-429 the readout for "was this
    caller throttled", which is exactly what these tests are asking.
    """
    media_router._rate_windows.clear()
    monkeypatch.setattr(media_router, "get_settings", lambda: _MediaSettings())

    app = FastAPI()
    app.include_router(media_router.router, prefix="/api/v1")

    db, storage = FakeMediaSession(), InMemoryStorage()

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[media_router.get_media_storage] = lambda: storage

    yield app
    media_router._rate_windows.clear()


def test_forged_header_no_longer_buys_a_fresh_window(limited, settings_cidrs):
    """Regression for the finding: an untrusted caller rotating
    ``X-Forwarded-For`` used to get a new 60s allowance per request."""
    settings_cidrs(DEFAULT)
    with TestClient(limited, client=(PUBLIC, 51234)) as client:
        codes = [
            client.get(
                f"/api/v1/media/tok{n}",
                headers={"x-forwarded-for": f"198.51.100.{n}"},
            ).status_code
            for n in range(1, 6)
        ]
    # Three allowed (they fall through to the resolver and 404), then the
    # window closes despite every request claiming a different origin.
    assert codes[:3] == [404, 404, 404]
    assert codes[3:] == [429, 429]


def test_a_real_proxy_still_gets_per_client_windows(limited, settings_cidrs):
    """The other half of the trade: distinct clients behind Caddy must
    not share one bucket, or a busy proxy throttles everybody at once."""
    settings_cidrs(DEFAULT)
    with TestClient(limited, client=(PRIVATE, 51234)) as client:
        codes = [
            client.get(
                f"/api/v1/media/tok{n}",
                headers={"x-forwarded-for": f"198.51.100.{n}"},
            ).status_code
            for n in range(1, 6)
        ]
    assert codes == [404] * 5
