from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import pytest

from backend import analytics
from backend.api.admin import analytics as admin_analytics
from backend.models.admin_user import AdminUser
from backend.models.event import Event
from backend.models.feature_event import FeatureEvent
from backend.services import feature_events


class _Row:
    def __init__(self, **values):
        self.__dict__.update(values)
        self._values = list(values.values())

    def __getitem__(self, index: int):
        return self._values[index]


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _FakeDB:
    def __init__(self, results):
        self.results = list(results)
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return self.results.pop(0)


def _admin(tenant_id: int | None = 1) -> AdminUser:
    return AdminUser(
        id=1,
        email="admin@example.com",
        password_hash="hash",
        role="super_admin",
        tenant_id=tenant_id,
        is_active=True,
    )


@pytest.mark.asyncio
async def test_record_feature_event_is_fire_and_forget_and_sanitizes(monkeypatch):
    captured = []

    async def fake_persist(feature_key, *, user_id, tenant_id, metadata):
        captured.append((feature_key, user_id, tenant_id, metadata))

    monkeypatch.setattr(feature_events, "_persist", fake_persist)

    feature_events.record_feature_event(
        "wealth_dashboard",
        tenant_id=7,
        metadata={"source": "menu", "phone": "secret", "note": "drop me"},
    )
    await asyncio.sleep(0)
    await feature_events.flush_pending(timeout=1.0)

    assert captured == [("wealth_dashboard", None, 7, {"source": "menu"})]


def test_feature_event_catalog_maps_existing_handlers():
    assert feature_events.feature_key_for_event("briefing_dashboard_clicked") == "wealth_dashboard"
    assert feature_events.feature_key_for_event("voice_transcribed") == "voice_query"
    assert feature_events.feature_key_for_event("goal_created") == "goal"
    assert feature_events.feature_name("miniapp") == "Mini App"


def test_mirror_feature_event_logs_warning_in_development(monkeypatch, caplog):
    monkeypatch.setattr(analytics, "feature_key_for_event", lambda *_: "miniapp")

    def boom(*_, **__):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(analytics, "record_feature_event", boom)
    monkeypatch.setattr(analytics, "get_settings", lambda: SimpleNamespace(environment="development"))

    with caplog.at_level(logging.WARNING):
        analytics._mirror_feature_event("miniapp_opened", None, {})

    assert "feature event mirror failed" in caplog.text


def test_tenant_filter_is_explicit_for_analytics_tables():
    assert str(admin_analytics._tenant_filter(FeatureEvent, 42)).startswith("feature_events.tenant_id")
    assert str(admin_analytics._tenant_filter(Event, 42)).startswith("events.tenant_id")


@pytest.mark.asyncio
async def test_feature_clicks_filters_by_admin_tenant_and_cache_key(monkeypatch):
    cache_get_keys = []
    cache_set_calls = []

    async def fake_cache_get(key):
        cache_get_keys.append(key)
        return None

    async def fake_cache_set(key, value, ttl):
        cache_set_calls.append((key, value, ttl))

    monkeypatch.setattr(admin_analytics, "cache_get", fake_cache_get)
    monkeypatch.setattr(admin_analytics, "cache_set", fake_cache_set)
    db = _FakeDB([_RowsResult([_Row(feature_key="miniapp", clicks=3)])])

    response = await admin_analytics.feature_clicks(days=7, limit=5, admin=_admin(42), db=db)

    assert response == {"data": [{"feature_key": "miniapp", "feature_name": "Mini App", "clicks": 3}]}
    assert cache_get_keys == ["admin:tenant:42:charts:feature-clicks:7:5"]
    assert cache_set_calls[0][2] == 1800
    assert "feature_events.tenant_id" in str(db.statements[0])


@pytest.mark.asyncio
async def test_intent_breakdown_normalizes_llm_and_calculates_percentages(monkeypatch):
    async def fake_cache_get(_key):
        return None

    async def fake_cache_set(*_args):
        return None

    monkeypatch.setattr(admin_analytics, "cache_get", fake_cache_get)
    monkeypatch.setattr(admin_analytics, "cache_set", fake_cache_set)
    db = _FakeDB([
        _RowsResult([_Row(resolved_by="rule", count=3), _Row(resolved_by="llm", count=1)]),
        _ScalarResult(1),
    ])

    response = await admin_analytics.intent_breakdown(days=7, admin=_admin(1), db=db)

    assert response["data"] == [
        {"resolved_by": "rule", "label": "Rule-based (zero cost)", "count": 3, "pct": 60.0},
        {"resolved_by": "llm_classifier", "label": "LLM classified", "count": 1, "pct": 20.0},
        {"resolved_by": "clarification", "label": "Cần clarify", "count": 1, "pct": 20.0},
    ]
