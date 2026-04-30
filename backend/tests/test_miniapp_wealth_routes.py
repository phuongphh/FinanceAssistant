"""Tests for the wealth dashboard route handlers (P3A-22).

Covers:
- 401 when ``X-Telegram-Init-Data`` header is missing or invalid.
- Happy path returns the composed payload.
- Cache TTL — second call within window returns cached value.
- /trend rejects unsupported ``days`` values with 422.
- Service errors map to a graceful 500 with friendly Vietnamese copy.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from backend.database import get_db
from backend.main import app
from backend.miniapp import routes as miniapp_routes
from backend.miniapp.auth import require_miniapp_auth

client = TestClient(app)


async def _stub_db():
    """Stand-in for ``get_db`` — wealth routes don't actually touch the
    DB once we mock ``_resolve_user`` and the service calls."""
    yield MagicMock()


def _fake_user(telegram_id: int = 12345):
    """Match the User shape that ``_resolve_user`` returns (id is enough)."""
    return SimpleNamespace(id=uuid.uuid4(), telegram_id=telegram_id)


def _override_auth(user_id: int = 12345):
    """Bypass HMAC verification — return a fake verified payload."""
    async def _ok():
        return {"user_id": user_id, "first_name": "Test"}

    app.dependency_overrides[require_miniapp_auth] = _ok
    app.dependency_overrides[get_db] = _stub_db


def _clear_overrides():
    app.dependency_overrides.pop(require_miniapp_auth, None)
    app.dependency_overrides.pop(get_db, None)
    miniapp_routes._wealth_cache_clear()


SAMPLE_OVERVIEW = {
    "net_worth": 5_000_000.0,
    "asset_count": 1,
    "currency": "VND",
    "level": "starter",
    "level_label": "Khởi đầu",
    "change_day": {"amount": 0.0, "pct": 0.0},
    "change_month": {"amount": 1_000_000.0, "pct": 25.0},
    "breakdown": [
        {
            "asset_type": "cash",
            "label": "Tiền mặt & Tài khoản",
            "icon": "💵",
            "color": "#10B981",
            "value": 5_000_000.0,
            "pct": 100.0,
        }
    ],
    "trend": [{"date": "2026-04-01", "value": 5_000_000.0}],
    "trend_days": 90,
    "assets": [
        {
            "id": "abc",
            "name": "VCB",
            "asset_type": "cash",
            "subtype": None,
            "icon": "💵",
            "type_label": "Tiền mặt & Tài khoản",
            "current_value": 5_000_000.0,
            "initial_value": 5_000_000.0,
            "change": 0.0,
            "change_pct": 0.0,
            "acquired_at": "2026-01-01",
        }
    ],
    "next_milestone": {
        "target": 30_000_000.0,
        "target_level": "young_prof",
        "target_label": "Young Professional",
        "pct_progress": 16.67,
        "remaining": 25_000_000.0,
    },
}


class TestWealthOverviewAuth:
    def setup_method(self):
        # Stub the DB dependency so failures don't bubble from auth →
        # database init when no DATABASE_URL is configured in CI.
        app.dependency_overrides[get_db] = _stub_db

    def teardown_method(self):
        _clear_overrides()

    def test_missing_init_data_returns_401(self):
        # No header → FastAPI raises 422 (Header(...) is required).
        resp = client.get("/miniapp/api/wealth/overview")
        assert resp.status_code in {401, 422}

    def test_invalid_init_data_returns_401(self):
        resp = client.get(
            "/miniapp/api/wealth/overview",
            headers={"X-Telegram-Init-Data": "invalid-data"},
        )
        assert resp.status_code == 401


class TestWealthOverviewHappyPath:
    def teardown_method(self):
        _clear_overrides()

    def test_returns_payload_and_caches(self):
        _override_auth()
        build_mock = AsyncMock(return_value=SAMPLE_OVERVIEW)
        # Stable user across both calls so the cache key matches.
        user = _fake_user()

        async def _fake_resolve(auth, db):
            return user

        with patch.object(miniapp_routes, "_resolve_user", _fake_resolve), \
             patch.object(
                 miniapp_routes.wealth_dashboard_service,
                 "build_overview",
                 build_mock,
             ):
            resp = client.get(
                "/miniapp/api/wealth/overview?source=briefing",
                headers={"X-Telegram-Init-Data": "stub"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["error"] is None
            assert body["data"]["net_worth"] == 5_000_000.0
            assert body["data"]["level"] == "starter"
            assert body["data"]["next_milestone"]["target"] == 30_000_000.0

            # Second call hits the cache — service NOT called twice.
            resp2 = client.get(
                "/miniapp/api/wealth/overview?source=briefing",
                headers={"X-Telegram-Init-Data": "stub"},
            )
            assert resp2.status_code == 200
            assert build_mock.await_count == 1

    def test_service_failure_returns_500(self):
        _override_auth()

        async def _fake_resolve(auth, db):
            return _fake_user()

        async def _boom(*args, **kwargs):
            raise RuntimeError("db blew up")

        with patch.object(miniapp_routes, "_resolve_user", _fake_resolve), \
             patch.object(
                 miniapp_routes.wealth_dashboard_service,
                 "build_overview",
                 _boom,
             ):
            resp = client.get(
                "/miniapp/api/wealth/overview",
                headers={"X-Telegram-Init-Data": "stub"},
            )
            assert resp.status_code == 500
            # Friendly copy in the detail — not a Python traceback.
            assert "tài sản" in resp.json()["detail"].lower()


class TestWealthTrendEndpoint:
    def teardown_method(self):
        _clear_overrides()

    def test_rejects_unsupported_days(self):
        _override_auth()

        async def _fake_resolve(auth, db):
            return _fake_user()

        with patch.object(miniapp_routes, "_resolve_user", _fake_resolve):
            resp = client.get(
                "/miniapp/api/wealth/trend?days=7",
                headers={"X-Telegram-Init-Data": "stub"},
            )
            assert resp.status_code == 422
            assert "30" in resp.json()["detail"]

    def test_happy_path_returns_trend(self):
        _override_auth()
        trend_mock = AsyncMock(return_value=[
            {"date": "2026-04-01", "value": 5_000_000.0},
            {"date": "2026-04-02", "value": 5_500_000.0},
        ])

        async def _fake_resolve(auth, db):
            return _fake_user()

        with patch.object(miniapp_routes, "_resolve_user", _fake_resolve), \
             patch.object(
                 miniapp_routes.wealth_dashboard_service,
                 "get_trend",
                 trend_mock,
             ):
            resp = client.get(
                "/miniapp/api/wealth/trend?days=90",
                headers={"X-Telegram-Init-Data": "stub"},
            )
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert len(data) == 2
            assert data[0]["value"] == 5_000_000.0


class TestStartAssetWizardRoute:
    def teardown_method(self):
        _clear_overrides()

    def test_invokes_wizard_with_user_telegram_id_as_chat_id(self):
        _override_auth()
        user = _fake_user(telegram_id=98765)

        async def _fake_resolve(auth, db):
            return user

        wizard_mock = AsyncMock()
        # Patch the symbol where it's imported — the route does a lazy
        # import inside the handler, so we patch the source module.
        with patch.object(miniapp_routes, "_resolve_user", _fake_resolve), \
             patch(
                 "backend.bot.handlers.asset_entry.start_asset_wizard",
                 wizard_mock,
             ):
            resp = client.post(
                "/miniapp/api/wealth/start-asset-wizard",
                headers={"X-Telegram-Init-Data": "stub"},
            )
            assert resp.status_code == 200
            assert resp.json() == {"data": {"ok": True}, "error": None}

            wizard_mock.assert_awaited_once()
            args = wizard_mock.await_args.args
            # (db, chat_id, user) — chat_id must equal user.telegram_id
            # so the bot posts the type-picker into the user's private chat.
            assert args[1] == 98765
            assert args[2] is user

    def test_requires_auth(self):
        # No auth override — the real require_miniapp_auth dependency
        # rejects the missing/invalid initData.
        app.dependency_overrides[get_db] = _stub_db
        try:
            resp = client.post(
                "/miniapp/api/wealth/start-asset-wizard",
                headers={"X-Telegram-Init-Data": "invalid"},
            )
            assert resp.status_code == 401
        finally:
            app.dependency_overrides.pop(get_db, None)


class TestWealthDashboardPage:
    def test_serves_html(self):
        resp = client.get("/miniapp/wealth")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        body = resp.text
        assert "Giá trị ròng" in body
        # Must reference the wealth-specific JS + CSS bundles.
        assert "wealth_dashboard.js" in body
        assert "wealth.css" in body
