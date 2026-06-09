"""Phase 4.3 admin cache freshness controls — unit tests.

Covers the operator-facing freshness improvements added on top of the
15-minute TTL cache:

- ``cache_invalidate_pattern`` SCAN+DEL behaviour & glob safety guard
- ``POST /twin-metrics/cache/invalidate`` tenant scoping + audit log
- ``cohort_week`` filter anchored to VN_TZ (Asia/Ho_Chi_Minh) midnight
- ``delta_distribution`` exposes ``calibration_meta`` with ``truncated``
- ``delta-distribution.csv`` surfaces total + truncated headers
- ``admin_cache_warmer`` iterates active tenants and pre-builds sections
"""

from __future__ import annotations

import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest
from sqlalchemy.dialects import postgresql

from backend.api.admin import twin_metrics
from backend.api.admin.analytics import VN_TZ
from backend.services import admin_cache


# ---------- helpers ----------------------------------------------------------


def _compile_sql(stmt) -> str:
    return str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


class _FakeAsyncRedis:
    """Minimal in-memory async Redis stub for cache_invalidate_pattern tests."""

    def __init__(self, keys: dict[str, str] | None = None):
        self.store: dict[str, str] = dict(keys or {})
        self.deleted: list[str] = []

    async def scan_iter(self, match: str, count: int = 200):
        import fnmatch
        for key in list(self.store.keys()):
            if fnmatch.fnmatch(key, match):
                yield key

    async def delete(self, key: str) -> int:
        if key in self.store:
            self.store.pop(key)
            self.deleted.append(key)
            return 1
        return 0


# ---------- cache_invalidate_pattern -----------------------------------------


@pytest.mark.asyncio
async def test_cache_invalidate_pattern_requires_glob(monkeypatch):
    # Even with a working client, a non-glob string must raise — the helper
    # is a bulk-delete primitive, never a single-key delete.
    monkeypatch.setattr(admin_cache, "_client", lambda: _FakeAsyncRedis())
    with pytest.raises(ValueError):
        await admin_cache.cache_invalidate_pattern("admin:tenant:1:twin:funnel:30d")
    with pytest.raises(ValueError):
        await admin_cache.cache_invalidate_pattern("")


@pytest.mark.asyncio
async def test_cache_invalidate_pattern_deletes_only_matches(monkeypatch):
    fake = _FakeAsyncRedis(keys={
        "admin:tenant:1:twin:funnel:30d:None:None": "{}",
        "admin:tenant:1:twin:loop:30d:None:None": "{}",
        # different tenant — must survive
        "admin:tenant:2:twin:funnel:30d:None:None": "{}",
        # unrelated app keys
        "session:u-1": "x",
    })
    monkeypatch.setattr(admin_cache, "_client", lambda: fake)

    removed = await admin_cache.cache_invalidate_pattern("admin:tenant:1:twin:*")

    assert removed == 2
    assert sorted(fake.deleted) == [
        "admin:tenant:1:twin:funnel:30d:None:None",
        "admin:tenant:1:twin:loop:30d:None:None",
    ]
    # Tenant 2 and unrelated keys remain.
    assert "admin:tenant:2:twin:funnel:30d:None:None" in fake.store
    assert "session:u-1" in fake.store


@pytest.mark.asyncio
async def test_cache_invalidate_pattern_swallows_redis_errors(monkeypatch):
    class _Broken:
        async def scan_iter(self, match, count=200):
            raise RuntimeError("redis down")
            yield  # pragma: no cover - generator marker

    monkeypatch.setattr(admin_cache, "_client", lambda: _Broken())
    # A Redis outage must NOT bubble up into the admin request path — the
    # next read just rebuilds the cache.
    assert await admin_cache.cache_invalidate_pattern("admin:tenant:1:*") == 0


# ---------- POST /cache/invalidate -------------------------------------------


@pytest.mark.asyncio
async def test_invalidate_endpoint_scopes_to_caller_tenant(monkeypatch):
    calls: list[str] = []

    async def fake_invalidate(pattern: str) -> int:
        calls.append(pattern)
        return 3

    audit_calls: list[dict] = []

    async def fake_log(db, admin_id, action, *, target_type, target_id, payload, request, commit):
        audit_calls.append({
            "admin_id": admin_id,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "payload": payload,
            "commit": commit,
        })
        return SimpleNamespace(id=1)

    monkeypatch.setattr(twin_metrics, "cache_invalidate_pattern", fake_invalidate)
    monkeypatch.setattr(twin_metrics, "log_action", fake_log)

    admin = SimpleNamespace(id=42, tenant_id=7)
    result = await twin_metrics.invalidate_twin_cache(
        sections=["funnel", "delta", "bogus"],
        request=None,
        admin=admin,
        db=SimpleNamespace(),
    )

    # Bogus sections are dropped; only the 2 valid sections get invalidated,
    # and every pattern is tenant-7-scoped (never wildcard across tenants).
    assert calls == [
        "admin:tenant:7:twin:funnel:*",
        "admin:tenant:7:twin:delta:*",
    ]
    assert result["tenant_id"] == 7
    assert result["sections"] == ["funnel", "delta"]
    assert result["keys_removed"] == 6
    # Audit MUST commit so the row survives even if the request errors after.
    assert audit_calls and audit_calls[0]["commit"] is True
    assert audit_calls[0]["action"] == "twin_cache_invalidate"
    assert audit_calls[0]["target_id"] == "7"


@pytest.mark.asyncio
async def test_invalidate_endpoint_defaults_to_all_sections(monkeypatch):
    calls: list[str] = []

    async def fake_invalidate(pattern: str) -> int:
        calls.append(pattern)
        return 1

    async def fake_log(*args, **kwargs):
        return SimpleNamespace(id=1)

    monkeypatch.setattr(twin_metrics, "cache_invalidate_pattern", fake_invalidate)
    monkeypatch.setattr(twin_metrics, "log_action", fake_log)

    admin = SimpleNamespace(id=1, tenant_id=None)  # falls back to DEFAULT_TENANT_ID
    result = await twin_metrics.invalidate_twin_cache(
        sections=None, request=None, admin=admin, db=SimpleNamespace(),
    )

    assert result["sections"] == list(twin_metrics.TWIN_SECTIONS)
    assert calls == [
        f"admin:tenant:{twin_metrics.DEFAULT_TENANT_ID}:twin:{section}:*"
        for section in twin_metrics.TWIN_SECTIONS
    ]


# ---------- cohort_week VN_TZ boundary ---------------------------------------


def test_user_filters_cohort_week_anchored_to_vn_tz():
    wealth_sq = twin_metrics._wealth_subquery()
    cohort = date(2026, 5, 18)  # Monday
    filters = twin_metrics._user_filters(tenant_id=1, cohort_week=cohort, segment=None, wealth_sq=wealth_sq)

    sql = " ".join(_compile_sql(f) for f in filters)

    # Bound values should be the UTC equivalent of midnight ICT on the
    # cohort start (00:00 ICT = 17:00 UTC previous day) so users who signed
    # up between 17:00-23:59 ICT are not silently excluded.
    expected_start = datetime.combine(cohort, time.min, tzinfo=VN_TZ).astimezone(timezone.utc)
    expected_end = expected_start + timedelta(days=7)
    # SQLAlchemy renders datetimes with a space separator (not ISO 'T'); match
    # the textual form actually emitted.
    start_literal = expected_start.strftime("%Y-%m-%d %H:%M:%S+00:00")
    end_literal = expected_end.strftime("%Y-%m-%d %H:%M:%S+00:00")
    assert start_literal in sql
    assert end_literal in sql
    # The naive UTC midnight would be 2026-05-18 00:00:00 — assert that we
    # are NOT using that, i.e. the timezone fix is live.
    assert "2026-05-18 00:00:00+00:00" not in sql


# ---------- delta_distribution calibration_meta ------------------------------


@pytest.mark.asyncio
async def test_delta_distribution_marks_truncated_when_total_exceeds_cap(monkeypatch):
    cap = twin_metrics.CALIBRATION_ROW_CAP
    rows_returned = cap  # at the cap
    rows_total = cap + 123  # more than cap

    class _DB:
        def __init__(self):
            self._scalar_queue = iter([rows_total])

        async def execute(self, stmt):
            text = _compile_sql(stmt)
            # threshold rows
            if "twin_delta_threshold_config" in text:
                return SimpleNamespace(all=lambda: [], scalar=lambda: 0)
            # recompute rows (delta histogram)
            if "FROM twin_recompute_log" in text and "delta_pct" in text and "GROUP BY" in text:
                return SimpleNamespace(all=lambda: [], scalar=lambda: 0)
            # projection rows
            if "FROM twin_projections" in text:
                return SimpleNamespace(all=lambda: [], scalar=lambda: 0)
            # calibration count query (COUNT + no LIMIT)
            if "twin_calibration_snapshots" in text and "count(" in text:
                return SimpleNamespace(all=lambda: [(rows_total,)], scalar=lambda: rows_total)
            # calibration list query (has ORDER BY + LIMIT)
            if "twin_calibration_snapshots" in text and "LIMIT" in text:
                rows = [(1_000_000.0, 1_050_000.0, True)] * rows_returned
                return SimpleNamespace(all=lambda rows=rows: rows, scalar=lambda: 0)
            return SimpleNamespace(all=lambda: [], scalar=lambda: 0)

    async def fake_cache_get(key):
        return None

    async def fake_cache_set(key, value, ttl):
        return None

    monkeypatch.setattr(twin_metrics, "cache_get", fake_cache_get)
    monkeypatch.setattr(twin_metrics, "cache_set", fake_cache_set)

    admin = SimpleNamespace(id=1, tenant_id=1)
    payload = await twin_metrics.delta_distribution(
        period="30d", start_date=None, end_date=None, segment=None,
        admin=admin, db=_DB(),
    )

    meta = payload["calibration_meta"]
    assert meta["cap"] == cap
    assert meta["rows_total"] == rows_total
    assert meta["rows_returned"] == rows_returned
    assert meta["truncated"] is True


# ---------- admin_cache_warmer -----------------------------------------------


@pytest.mark.asyncio
async def test_admin_cache_warmer_warms_every_active_tenant(monkeypatch):
    from backend.jobs import admin_cache_warmer

    fake_session = SimpleNamespace()

    class _Factory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return fake_session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    factory = _Factory()
    monkeypatch.setattr(admin_cache_warmer, "get_session_factory", lambda: factory)

    async def fake_active(db):
        assert db is fake_session
        return [1, 7]

    monkeypatch.setattr(admin_cache_warmer, "_active_tenant_ids", fake_active)

    calls: list[tuple[str, int]] = []

    async def make_call(label, tenant_id):
        calls.append((label, tenant_id))
        return {"ok": True}

    def _builders_factory(tenant_id):
        async def f_funnel(**kw):
            return await make_call("funnel", tenant_id)
        async def f_loop(**kw):
            return await make_call("loop", tenant_id)
        async def f_comp(**kw):
            return await make_call("comprehension", tenant_id)
        async def f_delta(**kw):
            return await make_call("delta", tenant_id)
        return f_funnel, f_loop, f_comp, f_delta

    # Patch each twin_metrics route to record the call instead of touching
    # the DB. We rebind by tenant via a closure over the current admin.
    async def fake_funnel(**kw):
        return await make_call("funnel", kw["admin"].tenant_id)
    async def fake_loop(**kw):
        return await make_call("loop", kw["admin"].tenant_id)
    async def fake_comp(**kw):
        return await make_call("comprehension", kw["admin"].tenant_id)
    async def fake_delta(**kw):
        return await make_call("delta", kw["admin"].tenant_id)

    monkeypatch.setattr(twin_metrics, "engagement_funnel", fake_funnel)
    monkeypatch.setattr(twin_metrics, "loop_health", fake_loop)
    monkeypatch.setattr(twin_metrics, "comprehension", fake_comp)
    monkeypatch.setattr(twin_metrics, "delta_distribution", fake_delta)

    summary = await admin_cache_warmer.run_admin_cache_warmer()

    assert summary == {"tenants": [1, 7], "sections_warmed": 8}
    # Every tenant got every section.
    assert sorted(calls) == sorted([
        ("funnel", 1), ("loop", 1), ("comprehension", 1), ("delta", 1),
        ("funnel", 7), ("loop", 7), ("comprehension", 7), ("delta", 7),
    ])


@pytest.mark.asyncio
async def test_admin_cache_warmer_continues_when_one_section_fails(monkeypatch):
    from backend.jobs import admin_cache_warmer

    class _Factory:
        async def __aenter__(self):
            return SimpleNamespace()
        async def __aexit__(self, exc_type, exc, tb):
            return False
    factory_instance = _Factory()
    monkeypatch.setattr(admin_cache_warmer, "get_session_factory", lambda: (lambda: factory_instance))

    async def fake_active(db):
        return [1]
    monkeypatch.setattr(admin_cache_warmer, "_active_tenant_ids", fake_active)

    async def boom(**kw):
        raise RuntimeError("loop section broken")
    async def ok(**kw):
        return {"ok": True}

    monkeypatch.setattr(twin_metrics, "engagement_funnel", ok)
    monkeypatch.setattr(twin_metrics, "loop_health", boom)
    monkeypatch.setattr(twin_metrics, "comprehension", ok)
    monkeypatch.setattr(twin_metrics, "delta_distribution", ok)

    summary = await admin_cache_warmer.run_admin_cache_warmer()
    # Three sections succeed; the broken one is counted as 0 but doesn't
    # poison the run.
    assert summary["tenants"] == [1]
    assert summary["sections_warmed"] == 3
