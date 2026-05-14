from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from backend.main import admin_api_rate_limit, settings


def test_admin_api_rate_limit_returns_429_after_configured_window(monkeypatch):
    monkeypatch.setattr(settings, "admin_api_rate_limit_per_minute", 2)
    app = FastAPI()
    app.middleware("http")(admin_api_rate_limit)

    @app.get("/api/admin/ping")
    async def ping():
        return JSONResponse({"ok": True})

    client = TestClient(app)
    headers = {"x-forwarded-for": "198.51.100.25"}

    assert client.get("/api/admin/ping", headers=headers).status_code == 200
    assert client.get("/api/admin/ping", headers=headers).status_code == 200
    response = client.get("/api/admin/ping", headers=headers)

    assert response.status_code == 429
    assert response.json()["detail"] == "Too many admin API requests"
