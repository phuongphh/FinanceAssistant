from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.twin.engine import ENGINE_VERSION
from backend.twin.schedulers import weekly_twin_updater
from backend.twin.services import (
    recompute_service,
    twin_projection_service,
    twin_query_service,
)
from backend.twin.services.twin_projection_service import PortfolioSnapshot


class FakeDB:
    def __init__(self):
        self.added = []
        self.flush_count = 0
        self.commit_count = 0
        self.rollback_count = 0

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flush_count += 1

    async def commit(self):
        self.commit_count += 1

    async def rollback(self):
        self.rollback_count += 1


@pytest.mark.asyncio
async def test_compute_and_store_writes_both_scenarios_without_commit(monkeypatch):
    user_id = uuid.uuid4()
    fake_db = FakeDB()

    async def fake_snapshot(db, uid):
        assert db is fake_db
        assert uid == user_id
        return PortfolioSnapshot(
            base_net_worth=Decimal("100000000"),
            monthly_savings=Decimal("5000000"),
            allocation_amounts={
                "stocks_vn": Decimal("70000000"),
                "cash_savings": Decimal("30000000"),
            },
            allocation_weights={
                "stocks_vn": Decimal("0.7000"),
                "cash_savings": Decimal("0.3000"),
            },
        )

    monkeypatch.setattr(
        twin_projection_service, "load_portfolio_snapshot", fake_snapshot
    )

    rows = await twin_projection_service.compute_and_store(
        fake_db,
        user_id,
        horizon=2,
        paths=20,
        seed=42,
    )

    assert len(rows) == 2
    assert {row.scenario for row in rows} == {"current", "optimal"}
    assert all(row.engine_version == ENGINE_VERSION for row in rows)
    assert (
        rows[0].cone_data[0]["p10"]
        == rows[0].cone_data[0]["p50"]
        == rows[0].cone_data[0]["p90"]
    )
    assert rows[1].monthly_savings == Decimal("5500000")
    assert fake_db.flush_count == 1
    assert fake_db.commit_count == 0


@pytest.mark.asyncio
async def test_twin_snapshot_handles_fresh_stale_and_missing(monkeypatch):
    user_id = uuid.uuid4()

    async def fake_calculate(db, uid):
        return SimpleNamespace(total=Decimal("105000000"))

    monkeypatch.setattr(
        twin_query_service.wealth_service, "calculate_stored_current", fake_calculate
    )

    fresh_projection = SimpleNamespace(
        computed_at=datetime.now(timezone.utc) - timedelta(days=2),
        cone_data=[{"year": 0, "p50": "100000000"}],
        horizon_years=10,
    )

    async def fresh_latest(db, uid, scenario=None):
        return fresh_projection

    monkeypatch.setattr(twin_query_service, "get_latest_projection", fresh_latest)
    fresh = await twin_query_service.get_twin_snapshot(FakeDB(), user_id)
    assert fresh.delta_vs_p50 == Decimal("5000000")
    assert fresh.is_stale is False

    stale_projection = SimpleNamespace(
        computed_at=datetime.now(timezone.utc) - timedelta(days=15),
        cone_data=[{"year": 0, "p50": "100000000"}],
        horizon_years=10,
    )

    async def stale_latest(db, uid, scenario=None):
        return stale_projection

    monkeypatch.setattr(twin_query_service, "get_latest_projection", stale_latest)
    stale = await twin_query_service.get_twin_snapshot(FakeDB(), user_id)
    assert stale.is_stale is True

    async def missing_latest(db, uid, scenario=None):
        return None

    monkeypatch.setattr(twin_query_service, "get_latest_projection", missing_latest)
    missing = await twin_query_service.get_twin_snapshot(FakeDB(), user_id)
    assert missing.latest_cone is None
    assert missing.delta_vs_p50 is None
    assert missing.is_stale is True


@pytest.mark.asyncio
async def test_recompute_enqueue_debounces_three_quick_edits(monkeypatch):
    user_id = uuid.uuid4()
    recompute_service._pending_user_ids.clear()

    async def fake_should(db, uid, delta):
        return uid not in recompute_service._pending_user_ids

    async def slow_background(uid):
        await asyncio.sleep(0.05)
        recompute_service._pending_user_ids.discard(uid)

    import asyncio

    monkeypatch.setattr(recompute_service, "should_recompute", fake_should)
    monkeypatch.setattr(recompute_service, "_compute_in_background", slow_background)

    first = await recompute_service.enqueue_recompute_if_needed(
        FakeDB(), user_id, Decimal("6000000")
    )
    second = await recompute_service.enqueue_recompute_if_needed(
        FakeDB(), user_id, Decimal("6000000")
    )
    third = await recompute_service.enqueue_recompute_if_needed(
        FakeDB(), user_id, Decimal("6000000")
    )

    assert (first, second, third) == (True, False, False)
    assert recompute_service.pending_recompute_count() == 1
    await asyncio.sleep(0.08)


@dataclass
class FakeUser:
    id: uuid.UUID


class FakeSessionFactory:
    def __init__(self):
        self.sessions = []

    def __call__(self):
        db = FakeDB()
        self.sessions.append(db)
        return FakeSessionContext(db)


class FakeSessionContext:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_weekly_updater_processes_five_users_with_isolated_commits(monkeypatch):
    users = [FakeUser(uuid.uuid4()) for _ in range(5)]
    factory = FakeSessionFactory()
    calls = []

    async def fake_active_users(db, days, require_telegram_id):
        assert days == 30
        assert require_telegram_id is False
        return users

    async def fake_compute(db, user_id, scenario):
        calls.append((db, user_id, scenario))

    monkeypatch.setattr(weekly_twin_updater, "get_session_factory", lambda: factory)
    monkeypatch.setattr(weekly_twin_updater, "get_active_users", fake_active_users)
    monkeypatch.setattr(weekly_twin_updater, "compute_and_store", fake_compute)
    monkeypatch.setattr(
        weekly_twin_updater.analytics, "track", lambda *args, **kwargs: None
    )

    metrics = await weekly_twin_updater.run_weekly_twin_update(concurrency_limit=2)

    assert metrics.total == 5
    assert metrics.succeeded == 5
    assert metrics.failed == 0
    assert len(calls) == 5
    assert all(scenario == "both" for _, _, scenario in calls)
    assert sum(db.commit_count for db in factory.sessions) == 5
