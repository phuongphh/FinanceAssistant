from __future__ import annotations

import gzip
import time
import uuid
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.adapters.chart_renderer import render_cone_chart
from backend.twin.engine.monte_carlo import simulate_portfolio
from backend.twin.schedulers import weekly_twin_updater
from backend.twin.services.twin_api_service import etag_for_payload


def _p95(samples: list[float]) -> float:
    ordered = sorted(samples)
    index = int(round((len(ordered) - 1) * 0.95))
    return ordered[index]


def test_single_user_monte_carlo_p95_under_two_seconds():
    allocation = {
        "stocks_vn": Decimal("300000000"),
        "stocks_global": Decimal("100000000"),
        "gold": Decimal("100000000"),
        "cash_savings": Decimal("75000000"),
        "crypto": Decimal("25000000"),
    }
    split = {
        "stocks_vn": Decimal("0.50"),
        "stocks_global": Decimal("0.15"),
        "gold": Decimal("0.15"),
        "cash_savings": Decimal("0.15"),
        "crypto": Decimal("0.05"),
    }
    samples = []
    for seed in range(5):
        start = time.perf_counter()
        result = simulate_portfolio(
            allocation,
            Decimal("15000000"),
            savings_split=split,
            horizon=10,
            paths=1000,
            seed=seed,
        )
        samples.append(time.perf_counter() - start)
        assert result.shape == (1000, 11)

    assert _p95(samples) < 2.0


@pytest.mark.asyncio
async def test_weekly_cron_100_users_under_five_minutes(monkeypatch):
    users = [SimpleNamespace(id=uuid.uuid4()) for _ in range(100)]

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def commit(self):
            return None

        async def rollback(self):
            return None

    def fake_session_factory():
        return FakeSession()

    async def fake_active_users(db, days, require_telegram_id):
        return users

    async def fake_compute_and_store(db, user_id, scenario):
        return None

    monkeypatch.setattr(
        weekly_twin_updater, "get_session_factory", lambda: fake_session_factory
    )
    monkeypatch.setattr(weekly_twin_updater, "get_active_users", fake_active_users)
    monkeypatch.setattr(
        weekly_twin_updater, "compute_and_store", fake_compute_and_store
    )
    monkeypatch.setattr(
        weekly_twin_updater.analytics, "track", lambda *args, **kwargs: None
    )

    start = time.perf_counter()
    metrics = await weekly_twin_updater.run_weekly_twin_update(concurrency_limit=10)
    elapsed = time.perf_counter() - start

    assert metrics.total == 100
    assert metrics.succeeded == 100
    assert metrics.failed == 0
    assert elapsed < 300


def test_chart_png_render_p95_under_500ms_after_warmup():
    cone = [
        {
            "year": year,
            "p10": 100_000_000 + year * 20_000_000,
            "p50": 120_000_000 + year * 30_000_000,
            "p90": 150_000_000 + year * 45_000_000,
        }
        for year in range(11)
    ]
    render_cone_chart(cone, width=400, height=300)
    samples = []
    for _ in range(5):
        start = time.perf_counter()
        png = render_cone_chart(cone, width=400, height=300)
        samples.append(time.perf_counter() - start)
        assert png.startswith(b"\x89PNG\r\n\x1a\n")

    assert _p95(samples) < 0.5


def test_cached_api_etag_p95_under_200ms():
    payload = {
        "scenario": "current",
        "computed_at": "2026-05-11T00:00:00+00:00",
        "actual_net_worth": "105000000",
        "engine_version": "4a.1.0",
    }
    samples = []
    for _ in range(50):
        start = time.perf_counter()
        etag = etag_for_payload(payload)
        samples.append(time.perf_counter() - start)
        assert etag.startswith('W/"twin-')

    assert _p95(samples) < 0.2


def test_miniapp_static_bundle_gzip_under_200kb():
    static_root = Path("backend/miniapp/static")
    payload = b"".join(
        path.read_bytes()
        for pattern in ("**/*.js", "**/*.css")
        for path in sorted(static_root.glob(pattern))
    )

    assert len(gzip.compress(payload)) < 200_000
