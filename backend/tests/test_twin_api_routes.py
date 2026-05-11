from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from backend.database import get_db
from backend.main import app
from backend.miniapp.auth import require_miniapp_auth
from backend.routers import twin as twin_router

client = TestClient(app)


async def _stub_db():
    yield MagicMock()


def _override_auth():
    async def _ok():
        return {"user_id": 12345, "first_name": "An"}

    app.dependency_overrides[require_miniapp_auth] = _ok
    app.dependency_overrides[get_db] = _stub_db


def _clear_overrides():
    app.dependency_overrides.pop(require_miniapp_auth, None)
    app.dependency_overrides.pop(get_db, None)


def _payload():
    return {
        "has_projection": True,
        "scenario": "current",
        "base_net_worth": "100000000",
        "actual_net_worth": "105000000",
        "delta_vs_p50": "5000000",
        "monthly_savings": "10000000",
        "allocation": {"stocks_vn": 0.6, "cash_savings": 0.4},
        "cone": [
            {"year": 0, "p10": "100000000", "p50": "100000000", "p90": "100000000"},
            {"year": 10, "p10": "150000000", "p50": "230000000", "p90": "360000000"},
        ],
        "computed_at": "2026-05-11T00:00:00+00:00",
        "cone_age_days": 0,
        "is_stale": False,
        "horizon_years": 10,
        "sim_paths": 1000,
        "engine_version": "4a.1.0",
    }


class TestTwinApiRoute:
    def teardown_method(self):
        _clear_overrides()

    def test_invalid_init_data_returns_401(self):
        app.dependency_overrides[get_db] = _stub_db
        resp = client.get("/api/twin", headers={"X-Telegram-Init-Data": "invalid"})
        assert resp.status_code == 401

    def test_returns_projection_json_and_etag(self):
        _override_auth()
        user = SimpleNamespace(id=uuid.uuid4(), telegram_id=12345)

        async def _fake_resolve(auth, db):
            return user

        async def _fake_payload(db, user_id, scenario="current"):
            assert scenario == "current"
            assert user_id == user.id
            return _payload()

        with patch.object(twin_router, "_resolve_user", _fake_resolve), patch.object(
            twin_router.twin_api_service, "build_twin_payload", _fake_payload
        ):
            resp = client.get("/api/twin?scenario=current", headers={"X-Telegram-Init-Data": "stub"})
            assert resp.status_code == 200
            assert resp.headers["etag"].startswith('W/"twin-')
            body = resp.json()
            assert body["error"] is None
            assert body["data"]["base_net_worth"] == "100000000"
            assert body["data"]["cone"][1]["p50"] == "230000000"

            resp2 = client.get(
                "/api/twin?scenario=current",
                headers={
                    "X-Telegram-Init-Data": "stub",
                    "If-None-Match": resp.headers["etag"],
                },
            )
            assert resp2.status_code == 304
            assert not resp2.content
