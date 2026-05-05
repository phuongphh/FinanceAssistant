"""Admin agent-metrics endpoint — auth + payload shape.

Avoids spinning up a real DB by patching ``get_db`` and the SQL
layer; the focus is on auth, response shape, and parameter validation.
End-to-end aggregation correctness is left for an integration test
once the test DB scaffolding is in place."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.config import get_settings
from backend.routers import admin_agent_metrics


@pytest.fixture
def app(monkeypatch):
    """Mount the admin router on a fresh FastAPI with a stubbed DB."""
    s = get_settings()
    monkeypatch.setattr(s, "internal_api_key", "test-secret")

    app = FastAPI()
    app.include_router(admin_agent_metrics.router, prefix="/api/v1")

    fake_db = _fake_db_with_canned_results()
    async def fake_get_db():
        yield fake_db

    from backend import database
    app.dependency_overrides[database.get_db] = fake_get_db
    return app


def _fake_db_with_canned_results():
    """Stub session: ``execute`` returns 0 results regardless of query."""
    db = MagicMock()
    one_result = MagicMock()
    one_result.count = 0
    one_result.cost = 0
    one_result.p95_latency = 0
    one_result.success_count = 0
    db.execute = AsyncMock()
    # Provide the right shape for each call:
    # .one() returns SimpleNamespace; .all() returns []; .scalars().all() returns [].
    one_obj = MagicMock()
    one_obj.one = MagicMock(return_value=one_result)
    one_obj.all = MagicMock(return_value=[])
    scalars = MagicMock()
    scalars.all = MagicMock(return_value=[])
    one_obj.scalars = MagicMock(return_value=scalars)
    db.execute.return_value = one_obj
    return db


class TestAuth:
    def test_missing_key_rejected(self, app):
        c = TestClient(app)
        r = c.get("/api/v1/admin/agent-metrics/today")
        assert r.status_code == 403

    def test_wrong_key_rejected(self, app):
        c = TestClient(app)
        r = c.get(
            "/api/v1/admin/agent-metrics/today",
            headers={"X-API-Key": "nope"},
        )
        assert r.status_code == 403

    def test_correct_key_accepted(self, app):
        c = TestClient(app)
        r = c.get(
            "/api/v1/admin/agent-metrics/today",
            headers={"X-API-Key": "test-secret"},
        )
        assert r.status_code == 200

    def test_unconfigured_returns_503(self, monkeypatch):
        # Build a fresh app with empty key.
        s = get_settings()
        monkeypatch.setattr(s, "internal_api_key", "")
        app = FastAPI()
        app.include_router(admin_agent_metrics.router, prefix="/api/v1")
        fake_db = _fake_db_with_canned_results()
        async def fake_get_db():
            yield fake_db
        from backend import database
        app.dependency_overrides[database.get_db] = fake_get_db

        c = TestClient(app)
        r = c.get(
            "/api/v1/admin/agent-metrics/today",
            headers={"X-API-Key": "anything"},
        )
        assert r.status_code == 503


class TestResponseShape:
    def test_today_returns_expected_keys(self, app):
        c = TestClient(app)
        r = c.get(
            "/api/v1/admin/agent-metrics/today",
            headers={"X-API-Key": "test-secret"},
        )
        body = r.json()
        for key in (
            "date", "total_queries", "total_cost_usd",
            "success_count", "p95_latency_ms", "tier_distribution",
        ):
            assert key in body

    def test_top_expensive_returns_list(self, app):
        c = TestClient(app)
        r = c.get(
            "/api/v1/admin/agent-metrics/top-expensive?limit=5",
            headers={"X-API-Key": "test-secret"},
        )
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_cost_trend_validates_days(self, app):
        c = TestClient(app)
        r = c.get(
            "/api/v1/admin/agent-metrics/cost-trend?days=0",
            headers={"X-API-Key": "test-secret"},
        )
        assert r.status_code == 400
        r = c.get(
            "/api/v1/admin/agent-metrics/cost-trend?days=999",
            headers={"X-API-Key": "test-secret"},
        )
        assert r.status_code == 400


class TestLimitGuard:
    def test_limit_validated(self, app):
        c = TestClient(app)
        r = c.get(
            "/api/v1/admin/agent-metrics/top-expensive?limit=0",
            headers={"X-API-Key": "test-secret"},
        )
        assert r.status_code == 400
        r = c.get(
            "/api/v1/admin/agent-metrics/top-expensive?limit=999",
            headers={"X-API-Key": "test-secret"},
        )
        assert r.status_code == 400
