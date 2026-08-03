"""Phase 5.0 #1.2 — the fail-closed boot check is actually wired in.

``assert_startup_invariant`` is unit-tested next door; what this file pins
is that ``backend.main``'s lifespan *calls* it, and calls it before the app
can serve anything. A correct helper nobody invokes is not a safeguard.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from backend import main as backend_main  # noqa: E402  (after importorskip)


@pytest.fixture()
def stub_lifespan(monkeypatch):
    """Neutralise everything in lifespan except the invariant check.

    The check sits before ``_wait_for_db``; stubbing the DB wait proves the
    ordering — if the assertion ever moved after it, this test would hang or
    fail on a missing database instead of raising.
    """

    async def _boom():  # pragma: no cover - only runs if ordering regresses
        raise AssertionError(
            "reached _wait_for_db — the Zalo invariant must be checked first"
        )

    monkeypatch.setattr(backend_main, "_wait_for_db", _boom)
    return backend_main.settings


async def _boot(app):
    async with backend_main.lifespan(app):  # pragma: no cover - never reached
        pass


@pytest.mark.asyncio
async def test_enabled_channel_without_secret_refuses_to_boot(
    stub_lifespan, monkeypatch
):
    monkeypatch.setattr(stub_lifespan, "zalo_channel_enabled", True)
    monkeypatch.setattr(stub_lifespan, "zalo_oa_secret_key", "")
    monkeypatch.setattr(stub_lifespan, "zalo_app_id", "app-1")

    with pytest.raises(RuntimeError) as exc:
        await _boot(backend_main.app)

    assert "ZALO_OA_SECRET_KEY" in str(exc.value)


@pytest.mark.asyncio
async def test_enabled_channel_without_app_id_refuses_to_boot(
    stub_lifespan, monkeypatch
):
    monkeypatch.setattr(stub_lifespan, "zalo_channel_enabled", True)
    monkeypatch.setattr(stub_lifespan, "zalo_oa_secret_key", "secret")
    monkeypatch.setattr(stub_lifespan, "zalo_app_id", "")

    with pytest.raises(RuntimeError) as exc:
        await _boot(backend_main.app)

    assert "ZALO_APP_ID" in str(exc.value)


@pytest.mark.asyncio
async def test_disabled_channel_boots_without_zalo_secrets(stub_lifespan, monkeypatch):
    """Telegram-only deployments must be unaffected by the new check."""
    monkeypatch.setattr(stub_lifespan, "zalo_channel_enabled", False)
    monkeypatch.setattr(stub_lifespan, "zalo_oa_secret_key", "")
    monkeypatch.setattr(stub_lifespan, "zalo_app_id", "")

    # Getting past the invariant means we hit the stubbed DB wait, which is
    # exactly the boundary this test cares about.
    with pytest.raises(AssertionError, match="reached _wait_for_db"):
        await _boot(backend_main.app)
