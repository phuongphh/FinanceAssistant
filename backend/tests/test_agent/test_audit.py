"""Audit log writer tests — mapping + fire-and-forget semantics."""
from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.agent import audit
from backend.agent.audit import RouteAudit


def _audit() -> RouteAudit:
    return RouteAudit(
        user_id=uuid.uuid4(),
        query_text="mã đang lãi?",
        tier_used="tier2",
        routing_reason="heuristic_tier2",
        tools_called=[{"name": "get_assets", "args": {"limit": 3}}],
        tool_call_count=1,
        llm_model="deepseek-chat",
        input_tokens=120,
        output_tokens=40,
        cost_usd=0.000128,
        success=True,
        response_preview="🟢 NVDA — 6.2 tỷ (+4.2%)",
        total_latency_ms=1850,
    )


class TestRouteAuditDataclass:
    def test_defaults_safe(self):
        a = RouteAudit(user_id=None, query_text="", tier_used="tier1")
        assert a.tools_called == []
        assert a.tool_call_count == 0
        assert a.success is False

    def test_to_dict_round_trips(self):
        d = audit.to_dict(_audit())
        assert d["tier_used"] == "tier2"
        assert d["tool_call_count"] == 1


class TestToRowMapping:
    def test_truncation_query_500plus(self):
        long = "x" * 3000
        a = RouteAudit(user_id=None, query_text=long, tier_used="tier1")
        row = audit._to_row(a)
        assert len(row.query_text) == 2000

    def test_truncation_response_preview(self):
        a = RouteAudit(
            user_id=None, query_text="?", tier_used="tier1",
            response_preview="y" * 1000,
        )
        row = audit._to_row(a)
        assert len(row.response_preview) == 500

    def test_empty_tools_stored_as_none(self):
        a = RouteAudit(user_id=None, query_text="?", tier_used="tier1")
        row = audit._to_row(a)
        assert row.tools_called is None  # None vs [] — JSONB friendlier

    def test_full_round_trip_fields(self):
        a = _audit()
        row = audit._to_row(a)
        assert row.user_id == a.user_id
        assert row.tier_used == "tier2"
        assert row.tool_call_count == 1
        assert row.input_tokens == 120
        assert row.output_tokens == 40
        assert row.cost_usd == 0.000128
        assert row.success is True


@pytest.mark.asyncio
class TestPersist:
    async def test_no_session_factory_silent(self, monkeypatch):
        # If get_session_factory raises, persist swallows.
        def boom():
            raise RuntimeError("no DB")
        monkeypatch.setattr(audit, "get_session_factory", boom)
        await audit._persist(_audit())  # must not raise

    async def test_writes_when_factory_available(self, monkeypatch):
        added = []

        class FakeSession:
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return None
            def add(self, x): added.append(x)
            async def commit(self): pass

        def factory():
            return FakeSession

        monkeypatch.setattr(audit, "get_session_factory", factory)
        await audit._persist(_audit())
        assert len(added) == 1
        assert added[0].tier_used == "tier2"


@pytest.mark.asyncio
class TestLogRouteFireAndForget:
    async def test_returns_immediately(self, monkeypatch):
        ran = asyncio.Event()
        original = audit._persist

        async def slow_persist(a):
            ran.set()
            await asyncio.sleep(0)  # yield
            await original(a)

        monkeypatch.setattr(audit, "_persist", slow_persist)
        # In an async test we have a running loop; log_route should
        # schedule a task and return without awaiting it.
        audit.log_route(_audit())
        # Yield once so the background task starts.
        await asyncio.sleep(0)
        assert ran.is_set()
