"""Unit tests for the intent_metrics aggregation helpers.

We don't run these against a real DB — instead we stub the
``AsyncSession.execute`` calls and assert the helpers produce the
right shape from canned rows. The SQL itself is exercised by the
admin-endpoint integration test in ``test_intent_metrics_route``.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services import intent_metrics


def _fake_db(execute_side_effect):
    db = MagicMock()
    db.execute = AsyncMock(side_effect=execute_side_effect)
    return db


def _scalar_result(value):
    res = MagicMock()
    res.scalar.return_value = value
    return res


def _rows_result(rows):
    res = MagicMock()
    res.all.return_value = rows
    return res


@pytest.mark.asyncio
async def test_daily_summary_counts_classifier_split():
    rule_row = MagicMock(classifier="rule", total=80)
    llm_row = MagicMock(classifier="llm", total=15)
    none_row = MagicMock(classifier="none", total=5)

    side_effects = [
        _rows_result([rule_row, llm_row, none_row]),  # classifier split
        _scalar_result(8),                             # unclear total
        _scalar_result(0.0123),                        # llm cost
        _scalar_result(45.6),                          # avg latency
    ]
    db = _fake_db(side_effects)

    summary = await intent_metrics.daily_summary(db)
    assert summary["total_classified"] == 100
    assert summary["by_classifier"]["rule"] == 80
    assert summary["by_classifier"]["llm"] == 15
    assert summary["by_classifier"]["none"] == 5
    assert summary["rule_rate"] == 0.8
    assert summary["unclear_total"] == 8
    assert summary["unclear_rate"] == 0.08
    assert summary["llm_cost_usd"] == pytest.approx(0.0123, rel=1e-3)
    assert summary["avg_latency_ms"] == 45.6


@pytest.mark.asyncio
async def test_daily_summary_handles_empty_window():
    """Zero events should yield zeros, NOT a divide-by-zero crash."""
    side_effects = [
        _rows_result([]),
        _scalar_result(0),
        _scalar_result(0.0),
        _scalar_result(0.0),
    ]
    db = _fake_db(side_effects)

    summary = await intent_metrics.daily_summary(db)
    assert summary["total_classified"] == 0
    assert summary["rule_rate"] == 0.0
    assert summary["unclear_rate"] == 0.0
    assert summary["llm_cost_usd"] == 0.0


@pytest.mark.asyncio
async def test_confidence_histogram_buckets():
    rows = [
        MagicMock(bucket="0.0-0.2", count=2),
        MagicMock(bucket="0.4-0.6", count=12),
        MagicMock(bucket="0.8-1.0", count=86),
    ]
    db = _fake_db([_rows_result(rows)])

    hist = await intent_metrics.confidence_histogram(db)
    assert hist["0.0-0.2"] == 2
    assert hist["0.2-0.4"] == 0
    assert hist["0.4-0.6"] == 12
    assert hist["0.8-1.0"] == 86


@pytest.mark.asyncio
async def test_top_unclear_intents():
    rows = [
        MagicMock(intent="query_assets", count=8),
        MagicMock(intent="advisory", count=5),
    ]
    db = _fake_db([_rows_result(rows)])

    top = await intent_metrics.top_unclear_intents(db, limit=10)
    assert top == [
        {"intent": "query_assets", "count": 8},
        {"intent": "advisory", "count": 5},
    ]


@pytest.mark.asyncio
async def test_cost_trend_groups_by_day():
    day_a = datetime(2026, 4, 28, tzinfo=timezone.utc)
    day_b = datetime(2026, 4, 29, tzinfo=timezone.utc)
    rows = [
        MagicMock(day=day_a, cost=0.012),
        MagicMock(day=day_b, cost=0.008),
    ]
    db = _fake_db([_rows_result(rows)])

    trend = await intent_metrics.cost_trend(db, days=7)
    assert trend == [
        {"day": "2026-04-28", "cost_usd": 0.012},
        {"day": "2026-04-29", "cost_usd": 0.008},
    ]


def test_evaluate_alerts_fires_for_high_cost():
    alerts = intent_metrics.evaluate_alerts({
        "total_classified": 200,
        "rule_rate": 0.8,
        "unclear_rate": 0.05,
        "llm_cost_usd": 0.75,
    })
    codes = {a["code"] for a in alerts}
    assert "llm_cost_high" in codes


def test_evaluate_alerts_fires_for_low_rule_rate():
    alerts = intent_metrics.evaluate_alerts({
        "total_classified": 200,
        "rule_rate": 0.3,
        "unclear_rate": 0.05,
        "llm_cost_usd": 0.0,
    })
    codes = {a["code"] for a in alerts}
    assert "rule_rate_low" in codes


def test_evaluate_alerts_fires_for_high_unclear_rate():
    alerts = intent_metrics.evaluate_alerts({
        "total_classified": 200,
        "rule_rate": 0.8,
        "unclear_rate": 0.30,
        "llm_cost_usd": 0.0,
    })
    codes = {a["code"] for a in alerts}
    assert "unclear_rate_high" in codes


def test_evaluate_alerts_quiet_for_small_volume():
    """Don't alarm when only a handful of queries have come through —
    statistics on tiny samples are noise."""
    alerts = intent_metrics.evaluate_alerts({
        "total_classified": 10,
        "rule_rate": 0.0,
        "unclear_rate": 1.0,
        "llm_cost_usd": 0.0,
    })
    assert alerts == []
