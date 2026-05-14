"""Tests for the per-session telegram_id→User cache in
``backend.services.dashboard_service``.

The cache exists to dedupe the 3-4 redundant ``SELECT users`` queries
the Telegram worker triggers per callback (issue #623). These tests
cover the contract the worker depends on:

- cache miss queries the DB; subsequent hits don't
- ``None`` (user-not-found) is cached too — repeat lookups for unknown
  telegram_ids stay in-process
- ``get_or_create_user`` seeds the cache so the post-creation
  ``stamp user_id on telegram_updates`` path skips the DB
- a session rollback drops the cache (cached ORM instances would
  otherwise be expired and trigger ``MissingGreenlet`` on attr access)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services import dashboard_service


def _make_fake_session(scalar_result):
    """Build a minimal AsyncSession-shaped mock backed by a dict ``info``."""
    sync_session = MagicMock()
    sync_session.info = {}
    db = MagicMock()
    db.info = sync_session.info  # AsyncSession.info proxies sync_session.info
    db.sync_session = sync_session
    exec_result = MagicMock()
    exec_result.scalar_one_or_none.return_value = scalar_result
    db.execute = AsyncMock(return_value=exec_result)
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_cache_hit_skips_second_query(monkeypatch):
    # Bypass the SQLAlchemy event registration — sync_session here is a
    # MagicMock, not a real Session, so event.listens_for would fail.
    monkeypatch.setattr(dashboard_service.event, "listens_for", lambda *_a, **_kw: (lambda f: f))

    fake_user = MagicMock(name="user", id="u1")
    db = _make_fake_session(scalar_result=fake_user)

    first = await dashboard_service.get_user_by_telegram_id(db, 42)
    second = await dashboard_service.get_user_by_telegram_id(db, 42)

    assert first is fake_user
    assert second is fake_user
    # One DB query for two calls.
    assert db.execute.await_count == 1


@pytest.mark.asyncio
async def test_cache_caches_none_for_unknown_user(monkeypatch):
    monkeypatch.setattr(dashboard_service.event, "listens_for", lambda *_a, **_kw: (lambda f: f))

    db = _make_fake_session(scalar_result=None)

    first = await dashboard_service.get_user_by_telegram_id(db, 99)
    second = await dashboard_service.get_user_by_telegram_id(db, 99)

    assert first is None and second is None
    # Caching ``None`` is the whole point — repeat unknown-id lookups
    # mustn't re-hit the DB (otherwise pre-registration users would
    # punch through the cache).
    assert db.execute.await_count == 1


@pytest.mark.asyncio
async def test_different_telegram_ids_are_isolated(monkeypatch):
    monkeypatch.setattr(dashboard_service.event, "listens_for", lambda *_a, **_kw: (lambda f: f))

    fake_user_a = MagicMock(name="ua")
    fake_user_b = MagicMock(name="ub")
    db = _make_fake_session(scalar_result=fake_user_a)
    db.execute.side_effect = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=fake_user_a)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=fake_user_b)),
    ]

    a = await dashboard_service.get_user_by_telegram_id(db, 1)
    b = await dashboard_service.get_user_by_telegram_id(db, 2)

    assert a is fake_user_a
    assert b is fake_user_b
    assert db.execute.await_count == 2


@pytest.mark.asyncio
async def test_get_or_create_user_seeds_cache(monkeypatch):
    monkeypatch.setattr(dashboard_service.event, "listens_for", lambda *_a, **_kw: (lambda f: f))

    # First call: user not found → triggers create branch.
    db = _make_fake_session(scalar_result=None)

    user, created = await dashboard_service.get_or_create_user(db, 100)

    assert created is True
    db.flush.assert_awaited_once()

    # Subsequent get_user_by_telegram_id must hit the cache, not the DB.
    cached = await dashboard_service.get_user_by_telegram_id(db, 100)
    assert cached is user
    # execute was called once (during the create's initial lookup).
    assert db.execute.await_count == 1


@pytest.mark.asyncio
async def test_rollback_listener_clears_cache(monkeypatch):
    """Verify the after_rollback callback drops the cache key.

    We capture the listener function registered by the service and
    invoke it directly with the sync_session — exactly what SQLAlchemy
    would do on a real rollback. After it runs, the next lookup must
    re-query.
    """
    captured = {}

    def fake_listens_for(target, event_name, **_kw):
        def decorator(fn):
            captured["fn"] = fn
            captured["event"] = event_name
            return fn
        return decorator

    monkeypatch.setattr(dashboard_service.event, "listens_for", fake_listens_for)

    fake_user = MagicMock(name="user")
    db = _make_fake_session(scalar_result=fake_user)

    await dashboard_service.get_user_by_telegram_id(db, 7)
    assert db.execute.await_count == 1
    assert captured["event"] == "after_rollback"

    # Simulate SQLAlchemy firing after_rollback.
    captured["fn"](db.sync_session)

    await dashboard_service.get_user_by_telegram_id(db, 7)
    # Cache was dropped, so the lookup re-queried.
    assert db.execute.await_count == 2
