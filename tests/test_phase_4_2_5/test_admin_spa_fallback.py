"""Regression test for issue #791 — admin SPA routes should fall back to
index.html instead of returning 404 from Starlette's StaticFiles.

The fix replaces ``StaticFiles(html=True)`` with a ``SPAStaticFiles``
subclass that catches the 404 raised for non-existent paths and serves
``index.html`` so the client-side router can handle the route.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

pytest.importorskip("starlette")
pytest.importorskip("fastapi")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.admin_spa import SPAStaticFiles


@pytest.fixture()
def spa_app(tmp_path: Path) -> TestClient:
    static_dir = tmp_path / "admin"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html>admin spa</html>")
    (static_dir / "favicon.ico").write_bytes(b"\x00")

    app = FastAPI()

    @app.get("/api/v1/ping")
    async def ping():
        return {"ok": True}

    app.mount("/", SPAStaticFiles(directory=str(static_dir), html=True), name="admin-spa")
    return TestClient(app)


def test_root_serves_index(spa_app: TestClient):
    resp = spa_app.get("/")
    assert resp.status_code == 200
    assert "admin spa" in resp.text


def test_real_asset_served_directly(spa_app: TestClient):
    resp = spa_app.get("/favicon.ico")
    assert resp.status_code == 200
    assert resp.content == b"\x00"


@pytest.mark.parametrize("path", ["/login", "/admin", "/admin/users", "/anything/deep"])
def test_spa_routes_fall_back_to_index(spa_app: TestClient, path: str):
    resp = spa_app.get(path)
    assert resp.status_code == 200, f"{path} returned {resp.status_code}"
    assert "admin spa" in resp.text


def test_api_route_still_wins_over_spa_mount(spa_app: TestClient):
    resp = spa_app.get("/api/v1/ping")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
