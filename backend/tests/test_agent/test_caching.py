"""Cache module tests — keying, TTL, JSON round-trip, invalidation.

DB-free: a fake AsyncSession captures ``add`` / ``execute`` and replays
canned ``LLMCache`` rows, mirroring the existing pattern used in
``test_asset_service.py``."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.agent import caching
from backend.models.llm_cache import LLMCache


def _expired_row():
    return LLMCache(
        cache_key="x", model="agent_tier2", prompt_hash="x",
        response="stale", expires_at=datetime.utcnow() - timedelta(minutes=1),
    )


def _fresh_row(value: str):
    return LLMCache(
        cache_key="x", model="agent_tier2", prompt_hash="x",
        response=value, expires_at=datetime.utcnow() + timedelta(minutes=10),
    )


def _mock_db(get_returns: object | None = None) -> MagicMock:
    """Returns a session whose ``execute`` returns ``get_returns``
    on a SELECT and a MagicMock on writes."""
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()

    def _exec_return(*args, **kwargs):
        result = MagicMock()
        result.scalar_one_or_none.return_value = get_returns
        result.rowcount = 1
        return result

    db.execute = AsyncMock(side_effect=_exec_return)
    return db


class TestKeyConstruction:
    def test_query_normalisation(self):
        # Whitespace + casing don't matter; semantics do.
        a = caching._query_hash("Mã đang lãi?")
        b = caching._query_hash("  mã đang lãi?  ")
        assert a == b

    def test_different_queries_different_keys(self):
        a = caching._query_hash("Mã đang lãi?")
        b = caching._query_hash("Mã đang lỗ?")
        assert a != b

    def test_keys_include_user(self):
        u1 = uuid.uuid4()
        u2 = uuid.uuid4()
        k1 = caching._key_tier2(u1, "x")
        k2 = caching._key_tier2(u2, "x")
        assert k1 != k2
        assert str(u1) in k1


@pytest.mark.asyncio
class TestTier2Cache:
    async def test_miss_returns_none(self):
        db = _mock_db(get_returns=None)
        out = await caching.get_tier2(
            db, user_id=uuid.uuid4(), query="anything"
        )
        assert out is None

    async def test_hit_round_trips_dict(self):
        # Pre-populate by stubbing the SELECT to return a fresh row.
        db = _mock_db(get_returns=_fresh_row('{"success": true, "count": 3}'))
        out = await caching.get_tier2(
            db, user_id=uuid.uuid4(), query="?"
        )
        assert out == {"success": True, "count": 3}

    async def test_corrupted_json_treated_as_miss(self):
        db = _mock_db(get_returns=_fresh_row("not-json"))
        out = await caching.get_tier2(
            db, user_id=uuid.uuid4(), query="?"
        )
        assert out is None

    async def test_set_writes_and_flushes(self):
        db = _mock_db()
        await caching.set_tier2(
            db, user_id=uuid.uuid4(), query="?", result={"x": 1}
        )
        # delete + insert + flush.
        assert db.execute.await_count >= 1  # the DELETE
        db.add.assert_called_once()
        db.flush.assert_awaited_once()
        added = db.add.call_args.args[0]
        assert isinstance(added, LLMCache)
        assert added.response == '{"x": 1}'
        # TTL bound — at most 5 minutes from now (slight slop).
        assert added.expires_at <= datetime.utcnow() + timedelta(seconds=305)


@pytest.mark.asyncio
class TestTier3Cache:
    async def test_set_uses_longer_ttl(self):
        db = _mock_db()
        await caching.set_tier3(
            db, user_id=uuid.uuid4(), query="?",
            response="đây là phân tích",
        )
        added = db.add.call_args.args[0]
        # 1 hour TTL — at least 50 minutes from now.
        assert added.expires_at >= datetime.utcnow() + timedelta(minutes=50)

    async def test_get_returns_response_text(self):
        db = _mock_db(get_returns=_fresh_row("Final answer here."))
        out = await caching.get_tier3(
            db, user_id=uuid.uuid4(), query="?"
        )
        assert out == "Final answer here."


@pytest.mark.asyncio
class TestInvalidation:
    async def test_pattern_delete_runs(self):
        db = _mock_db()
        n = await caching.invalidate_user(db, uuid.uuid4())
        assert n == 1  # rowcount from our mock
        # Single DELETE issued.
        assert db.execute.await_count == 1
