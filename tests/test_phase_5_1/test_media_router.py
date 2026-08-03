"""Phase 5.1 #1.3 — the public serving endpoint.

The DoD line under test: *"404 giống hệt nhau cho token sai / hết hạn /
đã revoke; không cache; rate limit; tắt cờ thì route không tồn tại."*

"Identical" is taken literally here: status, body bytes, and headers are
compared across the three misses rather than each being checked against
404 on its own. An endpoint whose 404s differ is an oracle — a visitor
holding a stale URL could confirm the account still exists, and anyone
probing could tell "wrong" from "used to be right".
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from tests.test_phase_5_1.conftest import FakeMediaSession, InMemoryStorage

pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.database import get_db  # noqa: E402
from backend.routers import media as media_router  # noqa: E402
from backend.services import media_url_service as svc  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"chart" * 20


class _Settings:
    media_rate_limit_per_minute = 120
    media_storage_path = "/unused"


@pytest.fixture()
def wired(monkeypatch):
    """An app with the media router mounted and its edges faked.

    Also clears the module-level rate-limit windows: they are
    process-global by design, so without this a test that exhausts the
    limit would poison whichever test ran next.
    """
    media_router._rate_windows.clear()
    settings = _Settings()
    monkeypatch.setattr(media_router, "get_settings", lambda: settings)

    db, storage = FakeMediaSession(), InMemoryStorage()

    app = FastAPI()
    app.include_router(media_router.router, prefix="/api/v1")

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[media_router.get_media_storage] = lambda: storage

    with TestClient(app) as client:
        yield client, db, storage, settings

    media_router._rate_windows.clear()


def _publish(db, storage, **kwargs):
    """Seed a published row from a synchronous test.

    ``TestClient`` drives the app on its own loop, so these tests are
    sync; ``asyncio.run`` gives the service the loop it needs without
    making every test in this module async for the sake of setup.
    """
    return asyncio.run(
        svc.publish(
            db,
            storage,
            user_id=uuid4(),
            data=kwargs.pop("data", PNG),
            content_type=kwargs.pop("content_type", "image/png"),
            **kwargs,
        )
    )


# ---------------------------------------------------------------------
# Hit
# ---------------------------------------------------------------------


def test_valid_token_serves_the_bytes(wired):
    client, db, storage, _ = wired

    published = _publish(db, storage)

    response = client.get(f"/api/v1/media/{published.token}")

    assert response.status_code == 200
    assert response.content == PNG
    assert response.headers["content-type"] == "image/png"


def test_response_is_never_cached_or_sniffed(wired):
    client, db, storage, _ = wired

    published = _publish(db, storage)

    response = client.get(f"/api/v1/media/{published.token}")

    assert response.headers["cache-control"] == "no-store, private"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_content_length_matches_the_body(wired):
    """Left to Starlette on purpose — a header taken from the row's
    ``byte_size`` would truncate the image if the two ever disagreed."""
    client, db, storage, _ = wired

    published = _publish(db, storage)

    response = client.get(f"/api/v1/media/{published.token}")

    assert int(response.headers["content-length"]) == len(response.content)


# ---------------------------------------------------------------------
# The four misses, indistinguishable
# ---------------------------------------------------------------------


def _misses(client, db, storage):
    """One response per way a lookup can fail."""
    unknown = client.get("/api/v1/media/definitely-not-a-token")

    expired = _publish(db, storage, ttl_seconds=60)
    db.rows[-1].expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    expired_response = client.get(f"/api/v1/media/{expired.token}")

    revoked = _publish(db, storage)
    db.rows[-1].deleted_at = datetime.now(timezone.utc)
    revoked_response = client.get(f"/api/v1/media/{revoked.token}")

    orphan = _publish(db, storage)
    storage.objects.pop(orphan.storage_key)
    orphan_response = client.get(f"/api/v1/media/{orphan.token}")

    return [unknown, expired_response, revoked_response, orphan_response]


def test_every_miss_is_the_same_404(wired):
    client, db, storage, _ = wired

    responses = _misses(client, db, storage)

    assert {r.status_code for r in responses} == {404}
    assert len({r.content for r in responses}) == 1


def test_misses_do_not_differ_in_their_headers(wired):
    """A ``Cache-Control`` or ``Content-Length`` that varied by cause
    would leak what the body refuses to."""
    client, db, storage, _ = wired

    responses = _misses(client, db, storage)

    fingerprints = {
        tuple(
            sorted(
                (name.lower(), value)
                for name, value in r.headers.items()
                if name.lower() not in {"date", "server"}
            )
        )
        for r in responses
    }
    assert len(fingerprints) == 1


def test_an_empty_token_is_not_a_media_route(wired):
    """``/api/v1/media/`` must not fall through to anything."""
    client, _, _, _ = wired

    assert client.get("/api/v1/media/").status_code in (307, 404, 405)


# ---------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------


def test_requests_past_the_limit_are_refused(wired):
    client, _, _, settings = wired
    settings.media_rate_limit_per_minute = 3

    codes = [
        client.get("/api/v1/media/whatever").status_code for _ in range(4)
    ]

    assert codes == [404, 404, 404, 429]


def test_the_limit_is_per_ip(wired):
    """Keyed on the first ``X-Forwarded-For`` hop, matching the admin
    limiter — production terminates TLS at a reverse proxy, so the
    socket address is the proxy's for everyone."""
    client, _, _, settings = wired
    settings.media_rate_limit_per_minute = 2

    for _ in range(2):
        client.get(
            "/api/v1/media/whatever", headers={"X-Forwarded-For": "1.1.1.1"}
        )

    exhausted = client.get(
        "/api/v1/media/whatever", headers={"X-Forwarded-For": "1.1.1.1"}
    )
    other = client.get(
        "/api/v1/media/whatever", headers={"X-Forwarded-For": "2.2.2.2"}
    )

    assert exhausted.status_code == 429
    assert other.status_code == 404


def test_rate_limit_response_says_nothing_about_the_token(wired):
    """429 is a statement about the caller's request rate, so it may not
    also become an existence check."""
    client, db, storage, settings = wired

    published = _publish(db, storage)
    settings.media_rate_limit_per_minute = 1
    client.get("/api/v1/media/whatever")

    real = client.get(f"/api/v1/media/{published.token}")
    fake = client.get("/api/v1/media/definitely-not-a-token")

    assert real.status_code == fake.status_code == 429
    assert real.content == fake.content


# ---------------------------------------------------------------------
# Off by default
# ---------------------------------------------------------------------


def test_media_url_is_off_by_default():
    from backend.config import Settings

    assert Settings().media_url_enabled is False


def test_the_route_does_not_exist_while_the_flag_is_off():
    """Unmounted means 404 for every token, which is also the correct
    answer — the feature is inert on the Telegram-only deployment."""
    from backend import main as backend_main

    paths = {getattr(route, "path", None) for route in backend_main.app.routes}
    if backend_main.settings.media_url_enabled:  # pragma: no cover
        pytest.skip("MEDIA_URL_ENABLED is on in this environment")
    assert "/api/v1/media/{token}" not in paths
