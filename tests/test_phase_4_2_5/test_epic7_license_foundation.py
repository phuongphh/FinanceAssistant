"""Phase 4.2.5 Epic 7 — License Foundation unit tests.

These tests intentionally avoid a live Postgres dependency while locking down
business contracts introduced by Epic 7:

- license model defaults / allowed states
- migration backfill + auto-create trigger SQL
- admin summary endpoint tenant scoping, deleted-user exclusion, cache behavior
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest
from sqlalchemy.dialects import postgresql


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDb:
    def __init__(self):
        self.scalar_values = [9, 8, 1]
        self.executed_scalars = []
        self.executed_queries = []

    async def scalar(self, stmt):
        self.executed_scalars.append(_compile_sql(stmt))
        return self.scalar_values.pop(0)

    async def execute(self, stmt):
        sql = _compile_sql(stmt)
        self.executed_queries.append(sql)
        if "GROUP BY licenses.plan" in sql:
            return _FakeResult(
                [
                    SimpleNamespace(key="free", count=7),
                    SimpleNamespace(key="pro", count=1),
                ]
            )
        if "GROUP BY licenses.status" in sql:
            return _FakeResult(
                [
                    SimpleNamespace(key="active", count=7),
                    SimpleNamespace(key="trialing", count=1),
                ]
            )
        raise AssertionError(f"Unexpected query: {sql}")


def _compile_sql(stmt) -> str:
    return str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def test_license_model_contract_matches_phase_425_foundation():
    from backend.models.license import (
        LICENSE_PLANS,
        LICENSE_STATUSES,
        PLAN_ENTERPRISE,
        PLAN_FOUNDING,
        PLAN_FREE,
        PLAN_PRO,
        STATUS_ACTIVE,
        STATUS_CANCELED,
        STATUS_EXPIRED,
        STATUS_PAST_DUE,
        STATUS_TRIALING,
        License,
    )

    assert License.__tablename__ == "licenses"
    assert LICENSE_PLANS == {PLAN_FREE, PLAN_PRO, PLAN_FOUNDING, PLAN_ENTERPRISE}
    assert LICENSE_STATUSES == {
        STATUS_ACTIVE,
        STATUS_TRIALING,
        STATUS_PAST_DUE,
        STATUS_CANCELED,
        STATUS_EXPIRED,
    }

    columns = License.__table__.c
    assert columns.user_id.unique is True
    assert columns.tenant_id.default.arg == 1
    assert columns.plan.default.arg == PLAN_FREE
    assert columns.status.default.arg == STATUS_ACTIVE
    assert {
        "trial_started_at",
        "trial_ends_at",
        "paid_started_at",
        "paid_ends_at",
    }.issubset(columns.keys())


def test_license_migration_backfills_and_auto_creates_free_license():
    migration = Path(
        "alembic/versions/20260518_phase425_license_foundation.py"
    ).read_text()

    assert "CREATE TRIGGER trg_users_create_free_license" in migration
    assert "AFTER INSERT ON users" in migration
    assert "EXECUTE FUNCTION create_free_license_for_user" in migration
    assert "VALUES (NEW.id, COALESCE(NEW.tenant_id, 1), 'free', 'active'" in migration
    assert "INSERT INTO licenses (user_id, tenant_id, plan, status" in migration
    assert "SELECT id, tenant_id, 'free', 'active'" in migration
    assert "WHERE deleted_at IS NULL" in migration
    assert "ON CONFLICT (user_id) DO NOTHING" in migration


@pytest.mark.asyncio
async def test_license_summary_returns_tenant_scoped_aggregate_payload(monkeypatch):
    from backend.api.admin import licenses as license_api

    cache_writes = []

    async def fake_cache_get(key):
        return None

    async def fake_cache_set(key, value, ttl_seconds):
        cache_writes.append((key, value, ttl_seconds))

    monkeypatch.setattr(license_api, "cache_get", fake_cache_get)
    monkeypatch.setattr(license_api, "cache_set", fake_cache_set)

    db = _FakeDb()
    admin = SimpleNamespace(tenant_id=42)
    response = await license_api.license_summary(admin=admin, db=db)

    assert response.total_users == 9
    assert response.total_licenses == 8
    assert response.missing_free_backfill == 1
    assert [(bucket.key, bucket.count) for bucket in response.plans] == [
        ("free", 7),
        ("pro", 1),
    ]
    assert [(bucket.key, bucket.count) for bucket in response.statuses] == [
        ("active", 7),
        ("trialing", 1),
    ]
    assert cache_writes[0][0] == "admin:tenant:42:licenses:summary"
    assert cache_writes[0][2] == 60
    assert cache_writes[0][1]["missing_free_backfill"] == 1

    all_sql = "\n".join(db.executed_scalars + db.executed_queries)
    assert "users.tenant_id = 42" in all_sql
    assert "licenses.tenant_id = 42" in all_sql
    assert "users.deleted_at IS NULL" in all_sql


@pytest.mark.asyncio
async def test_license_summary_uses_cached_payload_without_db(monkeypatch):
    from backend.api.admin import licenses as license_api

    cached = {
        "generated_at": "2026-05-14T00:00:00Z",
        "total_users": 1,
        "total_licenses": 1,
        "missing_free_backfill": 0,
        "plans": [{"key": "free", "count": 1}],
        "statuses": [{"key": "active", "count": 1}],
    }

    async def fake_cache_get(key):
        assert key == "admin:tenant:1:licenses:summary"
        return cached

    class NoDbAllowed:
        async def scalar(self, stmt):  # pragma: no cover - fail-fast guard
            raise AssertionError("DB should not be touched on cache hit")

        async def execute(self, stmt):  # pragma: no cover - fail-fast guard
            raise AssertionError("DB should not be touched on cache hit")

    monkeypatch.setattr(license_api, "cache_get", fake_cache_get)

    response = await license_api.license_summary(
        admin=SimpleNamespace(tenant_id=None),
        db=NoDbAllowed(),
    )

    assert response == cached
