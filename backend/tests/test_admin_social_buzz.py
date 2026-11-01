"""Hóng hớt #1061 — model, service and admin CRUD router.

CI has no database, so the router runs against :class:`FakeBuzzSession`,
which understands exactly the statements the service issues (matched on
compiled SQL) and fails loudly on anything else. Auth is *not* faked: the
real ``get_current_admin`` decodes a real admin JWT from
``backend.utils.admin_security``; only the Redis blacklist lookup and the
``AdminUser`` row come from the fake.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Select

from backend.api.admin import deps as admin_deps
from backend.config import get_settings
from backend.database import get_db
from backend.models.admin_audit_log import AdminAuditLog
from backend.models.admin_user import AdminUser
from backend.models.social_buzz_item import CATEGORIES, SOURCE_TYPES, SocialBuzzItem
from backend.routers import admin_social_buzz
from backend.services import social_buzz_service
from backend.utils.admin_security import create_admin_token

ADMIN_ID = 7


class FakeBuzzSession:
    def __init__(self) -> None:
        self.items: list[SocialBuzzItem] = []
        self.audit: list[AdminAuditLog] = []
        self.pending: list = []
        self.commits = 0
        self.flushes = 0
        self.admin = SimpleNamespace(id=ADMIN_ID, is_active=True, tenant_id=None)

    def add(self, row) -> None:
        self.pending.append(row)

    async def flush(self) -> None:
        self.flushes += 1
        now = datetime.now(timezone.utc)
        for row in self.pending:
            if isinstance(row, SocialBuzzItem):
                row.id = row.id or uuid.uuid4()
                # Strictly increasing so newest-first ordering is testable.
                row.created_at = row.created_at or now + timedelta(
                    microseconds=len(self.items)
                )
                row.updated_at = row.updated_at or row.created_at
                self.items.append(row)
            elif isinstance(row, AdminAuditLog):
                self.audit.append(row)
            else:
                raise AssertionError(f"unexpected add({type(row)})")
        self.pending = []

    async def commit(self) -> None:
        await self.flush()
        self.commits += 1

    async def refresh(self, row) -> None:
        return None

    async def get(self, model, key):
        if model is AdminUser:
            return self.admin if key == ADMIN_ID else None
        if model is SocialBuzzItem:
            return next((item for item in self.items if item.id == key), None)
        raise AssertionError(f"unexpected get({model})")

    def _filter(self, stmt: Select) -> list[SocialBuzzItem]:
        compiled = stmt.compile()
        text, params = str(compiled), compiled.params
        if "social_buzz_items.deleted_at IS NULL" not in text:
            raise AssertionError(f"list query must exclude deleted rows:\n{text}")
        rows = [item for item in self.items if item.deleted_at is None]
        if "social_buzz_items.category = " in text:
            rows = [item for item in rows if item.category == params["category_1"]]
        if "social_buzz_items.is_active IS true" in text:
            rows = [item for item in rows if item.is_active]
        if "social_buzz_items.is_active IS false" in text:
            rows = [item for item in rows if not item.is_active]
        return sorted(rows, key=lambda item: item.created_at, reverse=True)

    async def scalar(self, stmt):
        text = str(stmt.compile())
        if not text.startswith("SELECT count(*)"):
            raise AssertionError(f"unexpected scalar:\n{text}")
        inner = stmt.get_final_froms()[0].element
        return len(self._filter(inner))

    async def execute(self, stmt):
        if not isinstance(stmt, Select) or "FROM social_buzz_items" not in str(stmt.compile()):
            raise AssertionError(f"unexpected execute:\n{stmt}")
        compiled = stmt.compile()
        rows = self._filter(stmt)
        offset = compiled.params.get("param_2", 0)
        limit = compiled.params.get("param_1")
        rows = rows[offset:][:limit]
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: rows))


@pytest.fixture(autouse=True)
def admin_settings(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("ADMIN_JWT_SECRET", "test-secret-with-enough-entropy")
    monkeypatch.setenv("ADMIN_JWT_EXPIRY_MINUTES", "60")
    monkeypatch.setattr(admin_deps, "is_token_blacklisted", lambda jti: False)
    yield
    get_settings.cache_clear()


@pytest.fixture()
def db() -> FakeBuzzSession:
    return FakeBuzzSession()


@pytest.fixture()
def client(db):
    app = FastAPI()
    app.include_router(admin_social_buzz.router, prefix="/api/admin")

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    with TestClient(app) as test_client:
        yield test_client


def _auth(admin_id: int = ADMIN_ID, *, restricted: bool = False) -> dict[str, str]:
    token, _, _ = create_admin_token(admin_id, "ops@nuitruc.ai", "super_admin", restricted=restricted)
    return {"Authorization": f"Bearer {token}"}


def _create(client, **overrides):
    body = {
        "title": "Trend 'ăn mì tôm cả tháng' trên TikTok",
        "summary": "Gen Z rủ nhau tiết kiệm cực đoan.",
        "source_type": "tiktok",
        "category": "social",
        **overrides,
    }
    return client.post("/api/admin/social-buzz", json=body, headers=_auth())


# ── model ──────────────────────────────────────────────────────────────


def test_model_schema_matches_issue_contract():
    table = SocialBuzzItem.__table__
    assert table.name == "social_buzz_items"
    assert set(table.columns.keys()) >= {
        "id", "title", "summary", "url", "image_url", "source_type",
        "category", "is_active", "created_by", "created_at", "updated_at",
    }
    assert table.c.title.nullable is False
    for optional in ("summary", "url", "image_url"):
        assert table.c[optional].nullable is True
    assert table.c.url.unique is not True
    assert SOURCE_TYPES == ("thread", "tiktok", "manual")
    assert CATEGORIES == ("social", "tech", "economy")
    fk = next(iter(table.c.created_by.foreign_keys))
    assert fk.target_fullname == "admin_users.id"

    index = next(i for i in table.indexes if i.name == "ix_social_buzz_items_category_active_created")
    assert [c.name for c in index.columns] == ["category", "is_active", "created_at"]


def test_migration_targets_current_head_and_creates_table():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "20261026_social_buzz_items.py"
    spec = importlib.util.spec_from_file_location("mig_social_buzz", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.down_revision == "20260813zaloinflight"
    source = path.read_text(encoding="utf-8")
    assert '"social_buzz_items"' in source
    assert "ix_social_buzz_items_category_active_created" in source


# ── service ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_service_create_flushes_without_commit(db):
    item = await social_buzz_service.create_item(
        db, admin_id=ADMIN_ID, data={"title": "x", "source_type": "manual", "category": "tech"}
    )
    assert item.id is not None
    assert item.is_active is True
    assert item.created_by == ADMIN_ID
    assert db.flushes == 1 and db.commits == 0


# ── router: auth ───────────────────────────────────────────────────────


def test_missing_token_is_rejected(client, db):
    assert client.get("/api/admin/social-buzz").status_code == 401
    response = client.post("/api/admin/social-buzz", json={"title": "x", "category": "tech"})
    assert response.status_code == 401
    assert db.items == []


def test_invalid_token_is_rejected(client):
    response = client.get("/api/admin/social-buzz", headers={"Authorization": "Bearer not.a.jwt"})
    assert response.status_code == 401


def test_unknown_or_restricted_admin_is_forbidden(client, db):
    assert client.get("/api/admin/social-buzz", headers=_auth(admin_id=999)).status_code == 403
    restricted = client.get("/api/admin/social-buzz", headers=_auth(restricted=True))
    assert restricted.status_code == 403
    db.admin.is_active = False
    assert client.get("/api/admin/social-buzz", headers=_auth()).status_code == 403


# ── router: CRUD happy path ────────────────────────────────────────────


def test_create_persists_item_and_audits(client, db):
    response = _create(client, url="https://www.tiktok.com/@a/video/1", image_url=" ")

    assert response.status_code == 201
    body = response.json()
    assert body["title"].startswith("Trend")
    assert body["is_active"] is True
    assert body["created_by"] == ADMIN_ID
    assert body["image_url"] is None  # blank optional → NULL

    assert len(db.items) == 1
    assert db.items[0].url == "https://www.tiktok.com/@a/video/1"
    assert db.commits == 1
    assert [a.action for a in db.audit] == ["social_buzz_created"]
    assert db.audit[0].target_id == body["id"]


def test_create_without_url_is_allowed(client, db):
    response = _create(client, source_type="thread")
    assert response.status_code == 201
    assert response.json()["url"] is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"title": "   "},
        {"category": "sports"},
        {"source_type": "facebook"},
        {"url": "javascript:alert(1)"},
        {"image_url": "ftp://x/y.png"},
    ],
)
def test_create_rejects_invalid_payload(client, db, overrides):
    assert _create(client, **overrides).status_code == 422
    assert db.items == []


def test_list_filters_and_orders_newest_first(client):
    first = _create(client, title="A", category="tech").json()
    second = _create(client, title="B", category="tech").json()
    _create(client, title="C", category="economy")
    client.patch(f"/api/admin/social-buzz/{first['id']}", json={"is_active": False}, headers=_auth())

    everything = client.get("/api/admin/social-buzz", headers=_auth()).json()
    assert everything["total"] == 3
    assert [i["title"] for i in everything["items"]] == ["C", "B", "A"]

    active_tech = client.get(
        "/api/admin/social-buzz", params={"category": "tech", "is_active": "true"}, headers=_auth()
    ).json()
    assert active_tech["total"] == 1
    assert active_tech["items"][0]["id"] == second["id"]

    page = client.get("/api/admin/social-buzz", params={"limit": 1, "offset": 1}, headers=_auth()).json()
    assert page["total"] == 3
    assert [i["title"] for i in page["items"]] == ["B"]


def test_update_edits_fields_and_audits_names_only(client, db):
    created = _create(client, url="https://threads.net/p/1").json()
    db.commits = 0

    response = client.patch(
        f"/api/admin/social-buzz/{created['id']}",
        json={"title": "Tiêu đề mới", "url": None, "category": "economy"},
        headers=_auth(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Tiêu đề mới"
    assert body["url"] is None
    assert body["category"] == "economy"
    assert body["summary"] == created["summary"]  # omitted → untouched
    assert db.commits == 1
    assert db.audit[-1].action == "social_buzz_updated"
    assert db.audit[-1].payload == {"fields": ["category", "title", "url"]}


def test_hide_sets_is_active_false(client, db):
    created = _create(client).json()
    response = client.patch(
        f"/api/admin/social-buzz/{created['id']}", json={"is_active": False}, headers=_auth()
    )
    assert response.status_code == 200
    assert response.json()["is_active"] is False
    assert db.items[0].is_active is False
    assert db.items[0].deleted_at is None


def test_update_rejects_clearing_required_field(client):
    created = _create(client).json()
    response = client.patch(
        f"/api/admin/social-buzz/{created['id']}", json={"title": None}, headers=_auth()
    )
    assert response.status_code == 422


def test_noop_update_does_not_commit(client, db):
    created = _create(client).json()
    db.commits = 0
    response = client.patch(
        f"/api/admin/social-buzz/{created['id']}", json={"category": "social"}, headers=_auth()
    )
    assert response.status_code == 200
    assert db.commits == 0


def test_delete_is_soft_and_hides_from_portal(client, db):
    created = _create(client).json()

    response = client.delete(f"/api/admin/social-buzz/{created['id']}", headers=_auth())

    assert response.status_code == 204
    assert len(db.items) == 1 and db.items[0].deleted_at is not None  # row kept
    assert db.audit[-1].action == "social_buzz_deleted"
    assert client.get(f"/api/admin/social-buzz/{created['id']}", headers=_auth()).status_code == 404
    assert client.get("/api/admin/social-buzz", headers=_auth()).json()["total"] == 0
    assert client.delete(f"/api/admin/social-buzz/{created['id']}", headers=_auth()).status_code == 404


def test_unknown_item_is_404(client):
    missing = uuid.uuid4()
    assert client.get(f"/api/admin/social-buzz/{missing}", headers=_auth()).status_code == 404
    assert (
        client.patch(f"/api/admin/social-buzz/{missing}", json={"is_active": False}, headers=_auth()).status_code
        == 404
    )
