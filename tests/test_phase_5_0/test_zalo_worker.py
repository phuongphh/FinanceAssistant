"""Phase 5.0 #2.2 — dedup, dispatch, and orphan recovery.

The DoD line these cover: *"Tin nhắn Zalo trùng ``msg_id`` → xử lý đúng 1
lần (test retry)"*. Zalo redelivers anything it doesn't get a 2xx for, so
"exactly once" has to hold across two independent seams:

* the **router**, which claims the ``msg_id`` before enqueuing — a
  redelivery must not spawn a second task;
* the **orphan loop**, which re-enqueues rows stranded in ``processing``
  — two uvicorn workers scanning at once must not both dispatch the same
  row.

``aiosqlite`` isn't installed, so there is no ORM-backed session to test
against; the claim/dispatch contract is exercised through fakes that
reproduce the one behaviour that matters — ``rowcount`` from a
conditional write.
"""

from __future__ import annotations

import asyncio
import json
import logging
from uuid import uuid4

import pytest

pytest.importorskip("fastapi")

# noqa: E402 below — imports must follow the importorskip guard above.
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.dialects import postgresql  # noqa: E402
from sqlalchemy.sql.dml import Update  # noqa: E402

from backend.config import get_settings  # noqa: E402
from backend.database import get_db  # noqa: E402
from backend.models.zalo_update import (  # noqa: E402
    STATUS_DONE,
    STATUS_FAILED,
)
from backend.routers import zalo as zalo_router  # noqa: E402
from backend.workers import zalo_worker  # noqa: E402

APP_ID = "app-1234"
SENDER_ID = "zalo-sender-should-never-be-logged"
TIMESTAMP = "1754092800000"


_PG = postgresql.dialect()


def _params(stmt) -> dict:
    """Bind parameters of a statement, compiled for Postgres.

    The router builds a dialect-specific ``INSERT ... ON CONFLICT``, which
    the default dialect refuses to compile — so the fakes below have to
    ask for Postgres explicitly.
    """
    return stmt.compile(dialect=_PG).params


def _payload(text: str = "ăn trưa 50k", msg_id: str | None = "m-1") -> dict:
    body: dict = {
        "app_id": APP_ID,
        "event_name": "user_send_text",
        "timestamp": TIMESTAMP,
        "sender": {"id": SENDER_ID},
        "message": {"text": text},
    }
    if msg_id is not None:
        body["message"]["msg_id"] = msg_id
    return body


# --------------------------------------------------------------------------
# Router-level dedup: one claim, one task
# --------------------------------------------------------------------------


class _FakeClaimSession:
    """Records claims and rejects the second sight of a ``msg_id``.

    Stands in for ``INSERT ... ON CONFLICT DO NOTHING``: the first insert
    reports ``rowcount == 1``, every repeat reports 0.
    """

    def __init__(self, seen: set[str]) -> None:
        self.seen = seen
        self.commits = 0

    async def execute(self, stmt):
        msg_id = _params(stmt).get("msg_id")

        class _Result:
            rowcount = 0 if msg_id in self.seen else 1

        self.seen.add(msg_id)
        return _Result()

    async def commit(self) -> None:
        self.commits += 1


@pytest.fixture()
def dedup_client(monkeypatch):
    """Webhook client with a real ``_claim_update`` over a fake session.

    Signature verification is bypassed (no secret) so these tests speak
    only about dedup — the MAC has its own file.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "zalo_app_id", APP_ID)
    monkeypatch.setattr(settings, "zalo_oa_secret_key", "")

    enqueued: list[str] = []
    monkeypatch.setattr(
        zalo_router,
        "_enqueue_event",
        lambda msg_id, payload: enqueued.append(msg_id),
    )

    seen: set[str] = set()
    app = FastAPI()
    app.include_router(zalo_router.router, prefix="/api/v1")

    async def _fake_db():
        yield _FakeClaimSession(seen)

    app.dependency_overrides[get_db] = _fake_db
    return TestClient(app), enqueued


def _post(client: TestClient, payload: dict):
    return client.post(
        "/api/v1/zalo/webhook",
        content=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )


def test_redelivered_msg_id_is_processed_once(dedup_client):
    """The core retry guarantee: Zalo sends it twice, we act once."""
    client, enqueued = dedup_client
    payload = _payload()

    first = _post(client, payload)
    second = _post(client, payload)

    # Both are acked — a 500 on the retry would make Zalo keep retrying.
    assert first.status_code == 200
    assert second.status_code == 200
    assert enqueued == ["m-1"]


def test_distinct_messages_are_both_processed(dedup_client):
    client, enqueued = dedup_client

    _post(client, _payload("ăn trưa 50k", msg_id="m-1"))
    _post(client, _payload("cà phê 25k", msg_id="m-2"))

    assert enqueued == ["m-1", "m-2"]


def test_msg_id_less_events_dedup_on_the_derived_key(dedup_client):
    """No ``msg_id`` → the surrogate still collapses a redelivery."""
    client, enqueued = dedup_client
    payload = _payload(msg_id=None)

    _post(client, payload)
    _post(client, payload)

    assert len(enqueued) == 1
    assert enqueued[0].startswith("d:")


def test_duplicate_log_line_carries_no_sender_or_text(dedup_client, caplog):
    client, _ = dedup_client
    payload = _payload()
    _post(client, payload)

    with caplog.at_level(logging.INFO):
        _post(client, payload)

    blob = "\n".join(record.getMessage() for record in caplog.records)
    assert "Duplicate Zalo msg_id" in blob
    assert SENDER_ID not in blob
    assert "ăn trưa 50k" not in blob


def test_non_text_event_claims_no_row(dedup_client):
    """A ``follow`` event writes nothing — the table stays proportional
    to real conversation rather than to Zalo's whole event stream."""
    client, enqueued = dedup_client

    resp = _post(
        client,
        {
            "app_id": APP_ID,
            "event_name": "follow",
            "timestamp": TIMESTAMP,
            "sender": {"id": SENDER_ID},
        },
    )

    assert resp.status_code == 200
    assert enqueued == []


# --------------------------------------------------------------------------
# process_event_safely — never raises, always records
# --------------------------------------------------------------------------


@pytest.fixture()
def marks(monkeypatch) -> list[dict]:
    """Capture ``_mark_status`` calls instead of writing to Postgres."""
    calls: list[dict] = []

    async def _fake_mark(msg_id, status, *, error=None, user_id=None):
        calls.append(
            {"msg_id": msg_id, "status": status, "error": error, "user_id": user_id}
        )

    monkeypatch.setattr(zalo_worker, "_mark_status", _fake_mark)
    return calls


@pytest.mark.asyncio
async def test_successful_event_is_marked_done_with_its_user(monkeypatch, marks):
    user_id = uuid4()

    async def _fake_route(payload):
        return user_id

    monkeypatch.setattr(zalo_worker, "route_event", _fake_route)

    await zalo_worker.process_event_safely("m-1", _payload())

    assert marks == [
        {"msg_id": "m-1", "status": STATUS_DONE, "error": None, "user_id": user_id}
    ]


@pytest.mark.asyncio
async def test_handler_exception_never_escapes_the_task(monkeypatch, marks):
    """An unhandled handler bug must not kill the event loop — the
    webhook has already answered 200, there is nobody left to tell."""

    async def _boom(payload):
        raise RuntimeError("deepseek exploded")

    monkeypatch.setattr(zalo_worker, "route_event", _boom)

    await zalo_worker.process_event_safely("m-1", _payload())

    assert len(marks) == 1
    assert marks[0]["status"] == STATUS_FAILED
    assert "deepseek exploded" in marks[0]["error"]


@pytest.mark.asyncio
async def test_failure_does_not_clear_a_previously_resolved_user(monkeypatch, marks):
    """``user_id=None`` on the failure path means "don't touch it", not
    "set it to NULL" — otherwise a failed retry would erase the binding a
    successful first pass recorded."""

    async def _boom(payload):
        raise RuntimeError("boom")

    monkeypatch.setattr(zalo_worker, "route_event", _boom)

    await zalo_worker.process_event_safely("m-1", _payload())

    assert marks[0]["user_id"] is None


@pytest.mark.asyncio
async def test_error_message_is_truncated(monkeypatch, marks):
    async def _boom(payload):
        raise RuntimeError("x" * 5000)

    monkeypatch.setattr(zalo_worker, "route_event", _boom)

    await zalo_worker.process_event_safely("m-1", _payload())

    assert len(marks[0]["error"]) == 2000


# --------------------------------------------------------------------------
# route_event — payload that no longer parses
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unparseable_payload_is_dropped_not_raised(monkeypatch, caplog):
    """Recovery replays whatever is on the row. A row that no longer
    parses should end as ``done``-with-nothing, not as an endless retry."""
    monkeypatch.setattr(get_settings(), "zalo_app_id", APP_ID)

    with caplog.at_level(logging.WARNING):
        result = await zalo_worker.route_event({"not": "an event"})

    assert result is None
    assert "unusable payload" in "\n".join(
        record.getMessage() for record in caplog.records
    )


# --------------------------------------------------------------------------
# Orphan recovery — single winner under concurrency
# --------------------------------------------------------------------------


class _FakeOrphanSession:
    """Serves one candidate row and lets exactly one claim succeed."""

    def __init__(self, rows: list[tuple[str, dict]], claimed: set[str]) -> None:
        self.rows = rows
        self.claimed = claimed
        self.commits = 0

    async def execute(self, stmt):
        if isinstance(stmt, Update):
            # The conditional claim. Its WHERE pins one msg_id; whoever
            # gets there first wins, exactly as the row lock decides in
            # Postgres.
            msg_id = _params(stmt).get("msg_id_1")
            won = msg_id not in self.claimed
            self.claimed.add(msg_id)

            class _UpdateResult:
                rowcount = 1 if won else 0

            return _UpdateResult()

        rows = self.rows

        class _SelectResult:
            def all(self):
                return rows

        return _SelectResult()

    async def commit(self) -> None:
        self.commits += 1

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.mark.asyncio
async def test_orphan_is_claimed_by_exactly_one_worker(monkeypatch):
    """Two processes scanning the same stale row must dispatch it once."""
    rows = [("m-orphan", _payload())]
    claimed: set[str] = set()

    monkeypatch.setattr(
        zalo_worker,
        "get_session_factory",
        lambda: lambda: _FakeOrphanSession(rows, claimed),
    )

    spawned: list[str] = []
    processed = asyncio.Event()

    async def _fake_process(msg_id, payload):
        spawned.append(msg_id)
        processed.set()

    monkeypatch.setattr(zalo_worker, "process_event_safely", _fake_process)

    first = await zalo_worker.recover_orphaned_events()
    second = await zalo_worker.recover_orphaned_events()

    # Let the spawned task(s) run before asserting.
    await asyncio.sleep(0)

    assert first == 1
    assert second == 0
    assert spawned == ["m-orphan"]


@pytest.mark.asyncio
async def test_recovery_loop_survives_a_failing_pass(monkeypatch, caplog):
    """One bad pass must not silently disable recovery for the rest of
    the process's life."""
    calls = {"n": 0}

    async def _flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("db down")
        raise asyncio.CancelledError()

    monkeypatch.setattr(zalo_worker, "recover_orphaned_events", _flaky)

    async def _no_sleep(_seconds):
        return None

    monkeypatch.setattr(zalo_worker.asyncio, "sleep", _no_sleep)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(asyncio.CancelledError):
            await zalo_worker.run_recovery_loop(interval_seconds=0)

    assert calls["n"] == 2
    assert "recovery pass failed" in "\n".join(
        record.getMessage() for record in caplog.records
    )


# --------------------------------------------------------------------------
# route_event — the 48h reply window opens before the handler runs
# --------------------------------------------------------------------------


class _SessionFactory:
    """Hands ``route_event`` one recording session per ``async with``."""

    def __init__(self, session) -> None:
        self.session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *exc_info) -> bool:
        return False


@pytest.fixture()
def routed(monkeypatch, window_store):
    """Run ``route_event`` against the in-memory window store.

    Returns an invoker: ``await routed(user_id=...)`` → the store, whose
    ``events`` list is the ordered log of what touched the session.
    """
    monkeypatch.setattr(get_settings(), "zalo_app_id", APP_ID)
    monkeypatch.setattr(
        zalo_worker, "get_session_factory", lambda: _SessionFactory(window_store)
    )

    async def _invoke(*, user_id=None, payload=None):
        from backend.bot.handlers import zalo_inbound

        async def _fake_handle(db, *, event):
            window_store.events.append("handle")
            return user_id

        monkeypatch.setattr(zalo_inbound, "handle_inbound_event", _fake_handle)
        await zalo_worker.route_event(payload or _payload())
        return window_store

    return _invoke


@pytest.mark.asyncio
async def test_the_window_is_committed_before_the_handler_runs(routed):
    """The ordering that makes a reply to a first message possible.

    ``reserve_send`` runs in its own committed transaction, so it cannot
    see a window this session has only flushed. If the upsert rode the
    final commit, every first reply would be refused ``no_window``.
    """
    store = await routed()

    assert store.events[:3] == ["record_inbound", "commit", "handle"]


@pytest.mark.asyncio
async def test_a_linked_sender_is_bound_on_the_final_commit(routed):
    user_id = uuid4()

    store = await routed(user_id=user_id)

    assert store.events == [
        "record_inbound",
        "commit",
        "handle",
        "bind_user",
        "commit",
    ]
    assert store.rows[SENDER_ID].user_id == user_id


@pytest.mark.asyncio
async def test_an_unlinked_sender_still_gets_a_window(routed):
    """Someone can message the OA before ever linking an account — the
    window is about the *conversation*, not about having a user row."""
    store = await routed(user_id=None)

    assert "bind_user" not in store.events
    assert store.rows[SENDER_ID].user_id is None
    assert store.rows[SENDER_ID].window_expires_at is not None


@pytest.mark.asyncio
async def test_a_failing_handler_leaves_the_window_open(routed, monkeypatch):
    """The window commit is deliberately not rolled back with the handler.

    Zalo already counts the inbound message as opening the window, so
    dropping our copy would only desync us from the platform — and the
    row expires on its own in 48h either way.
    """
    from backend.bot.handlers import zalo_inbound

    async def _boom(db, *, event):
        raise RuntimeError("classifier exploded")

    monkeypatch.setattr(zalo_inbound, "handle_inbound_event", _boom)

    with pytest.raises(RuntimeError):
        await zalo_worker.route_event(_payload())

    # ``routed`` installed the store + settings; the window survived the
    # handler blowing up because it was committed before dispatch.
    assert zalo_worker.get_session_factory().session.commits == 1
