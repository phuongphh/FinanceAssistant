"""Make the repository root importable for the Phase 5.0 suite.

``tests/`` has no ``__init__.py`` but ``tests/test_phase_5_0/`` does, so
pytest's rootdir insertion stops at ``tests/`` and a bare ``import backend``
fails. Older suites work around that by inlining a ``sys.path`` fix in every
test module, which forces the real imports below it and trips ``E402``.

pytest imports ``conftest.py`` before any test module in the package, so
doing the fix once here lets each test file keep its imports at the top.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402  — must follow the sys.path fix above
from sqlalchemy.dialects import postgresql  # noqa: E402

_PG = postgresql.dialect()


class FakeWindowRow:
    """One ``zalo_message_window`` row, as the fake store keeps it."""

    def __init__(self, zalo_user_id: str) -> None:
        self.zalo_user_id = zalo_user_id
        self.user_id = None
        self.last_inbound_at = None
        self.window_expires_at = None
        self.free_msg_count = 0
        self.last_sent_at = None


class FakeWindowStore:
    """In-memory stand-in for the ``zalo_message_window`` table.

    ``aiosqlite`` isn't installed and there is no Postgres in CI, so the
    window service is exercised against this rather than an ORM session.

    The store re-implements the four statements by hand, which is only
    trustworthy because ``test_zalo_window_service.py`` also compiles the
    real statements and asserts their WHERE/SET clauses verbatim. If the
    service's SQL and this simulation drift apart, those shape tests fail
    first — they are what pins the behaviour; this is what makes
    sequences (open → spend → re-open) testable.

    What it deliberately does *not* model is Postgres row locking: every
    call here runs to completion before the next one starts. The claim
    that two racing reservations can't both take the eighth slot is a
    property of ``UPDATE ... WHERE free_msg_count < 8`` under READ
    COMMITTED, and is asserted on the compiled SQL, not here.
    """

    def __init__(self) -> None:
        self.rows: dict[str, FakeWindowRow] = {}
        self.statements: list[str] = []
        self.commits = 0
        self.flushes = 0
        # Ordered log of everything that touched the session, so a test
        # can assert *sequence* and not just totals — the worker's
        # "window committed before the handler runs" ordering is the
        # whole point of #3.1's wiring and is invisible to counters.
        self.events: list[str] = []
        # Params of every ``zalo_updates`` write the worker made through
        # this session. The success stamp rides the handler's own
        # transaction (#7), so it shows up here rather than in the
        # ``_mark_status`` spy — and its position in ``events`` relative
        # to ``commit`` is the whole claim.
        self.marked: list[dict] = []

    # -- session surface ---------------------------------------------------

    async def execute(self, stmt):
        compiled = stmt.compile(dialect=_PG)
        sql = str(compiled)
        params = compiled.params
        self.statements.append(sql)

        if "zalo_updates" in sql:
            self.events.append("mark_done")
            self.marked.append(params)
            return _FakeResult(rowcount=1)
        if "ON CONFLICT" in sql:
            self.events.append("record_inbound")
            return self._upsert(params)
        if sql.startswith("SELECT"):
            self.events.append("select")
            return self._select(params)
        if "free_msg_count + " in sql:
            self.events.append("reserve")
            return self._reserve(params)
        if "free_msg_count - " in sql:
            self.events.append("release")
            return self._release(params)
        if "SET user_id" in sql:
            self.events.append("bind_user")
            return self._bind(params)
        raise AssertionError(f"FakeWindowStore saw an unmodelled statement: {sql}")

    async def flush(self) -> None:
        self.flushes += 1

    async def commit(self) -> None:
        # The window *service* must never land here — the boundary test
        # and ``test_*_does_not_commit`` both assert this stays 0 for
        # service-only sequences. The worker, which owns the transaction
        # boundary, legitimately does; that is what ``events`` records.
        self.commits += 1
        self.events.append("commit")

    # -- statement simulations ---------------------------------------------

    def _upsert(self, params):
        key = params["zalo_user_id"]
        row = self.rows.setdefault(key, FakeWindowRow(key))
        moment = params["last_inbound_at"]
        # The three CASE arms: the window only moves forward. A NULL
        # ``last_inbound_at`` counts as newer — the row exists but has
        # never seen a message, so there is no window to protect.
        if row.last_inbound_at is None or row.last_inbound_at < moment:
            row.last_inbound_at = moment
            row.window_expires_at = params["window_expires_at"]
            row.free_msg_count = params["free_msg_count"]
        # coalesce(excluded.user_id, zalo_message_window.user_id) — set
        # outside the CASE, so a stale inbound can still teach us who the
        # sender is without reopening their window.
        row.user_id = params["user_id"] or row.user_id
        # RETURNING window_expires_at — what is *stored*, not what was
        # offered, which is the difference the monotonic guard creates.
        return _FakeResult(rowcount=1, scalar=row.window_expires_at)

    def _bind(self, params):
        row = self.rows.get(params["zalo_user_id_1"])
        if row is None or row.user_id is not None:
            return _FakeResult(rowcount=0)
        row.user_id = params["user_id"]
        return _FakeResult(rowcount=1)

    def _reserve(self, params):
        row = self.rows.get(params["zalo_user_id_1"])
        if row is None:
            return _FakeResult(rows=[])
        if (
            not row.window_expires_at
            or row.window_expires_at <= params["window_expires_at_1"]
        ):
            return _FakeResult(rows=[])
        if row.free_msg_count >= params["free_msg_count_2"]:
            return _FakeResult(rows=[])
        row.free_msg_count += params["free_msg_count_1"]
        row.last_sent_at = params["last_sent_at"]
        return _FakeResult(
            rows=[_FakeRow(row.free_msg_count, row.window_expires_at)], rowcount=1
        )

    def _release(self, params):
        row = self.rows.get(params["zalo_user_id_1"])
        if row is None:
            return _FakeResult(rowcount=0)
        if row.window_expires_at != params["window_expires_at_1"]:
            return _FakeResult(rowcount=0)
        if row.free_msg_count <= params["free_msg_count_2"]:
            return _FakeResult(rowcount=0)
        row.free_msg_count -= params["free_msg_count_1"]
        return _FakeResult(rowcount=1)

    def _select(self, params):
        row = self.rows.get(params["zalo_user_id_1"])
        if row is None:
            return _FakeResult(rows=[])
        return _FakeResult(
            rows=[_FakeRow(row.free_msg_count, row.window_expires_at)], rowcount=1
        )


class _FakeRow:
    def __init__(self, free_msg_count, window_expires_at) -> None:
        self.free_msg_count = free_msg_count
        self.window_expires_at = window_expires_at


class _FakeResult:
    def __init__(self, rows=None, rowcount: int = 0, scalar=None) -> None:
        self._rows = rows or []
        self.rowcount = rowcount
        self._scalar = scalar

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar_one_or_none(self):
        # ``record_inbound`` reads the RETURNING column this way. The
        # monotonic upsert always writes *something*, so a real Postgres
        # always yields a row here — ``None`` would mean the statement
        # matched nothing, which the CASE-based form cannot produce.
        return self._scalar


@pytest.fixture()
def window_store() -> FakeWindowStore:
    """A fresh in-memory ``zalo_message_window`` per test."""
    return FakeWindowStore()


class FakeMetricsSession:
    """Answers the aggregate queries in ``zalo_quota_metrics`` (#3.3).

    Deliberately dumber than :class:`FakeWindowStore`: those are read-only
    ``GROUP BY``/``count()`` statements with no state to simulate, so this
    only has to route each one to a canned answer. It routes on the
    *compiled* SQL rather than on call order, so a query that changes
    shape lands in the wrong branch and fails loudly instead of quietly
    returning the previous query's numbers.

    ``delivered`` may be an int (every interval answers the same) or a
    list consumed in order — the snapshot asks twice when a baseline is
    supplied, once over the lookback window and once over the baseline's
    own interval, and telling those two apart is the point of several
    tests. Every ``since`` it was asked for is recorded in
    :attr:`delivered_since`.
    """

    def __init__(self, *, blocked=None, delivered=0, ledger=None) -> None:
        self.blocked = dict(blocked or {})
        self.delivered = delivered
        self.ledger = {
            "tracked_senders": 0,
            "open_windows": 0,
            "exhausted_windows": 0,
            "slots_used_open": 0,
            **(ledger or {}),
        }
        self.delivered_since: list = []
        self.statements: list[str] = []
        self.commits = 0

    async def execute(self, stmt):
        compiled = stmt.compile(dialect=_PG)
        sql = str(compiled)
        self.statements.append(sql)

        if "zalo_message_window" in sql:
            return _FakeAggregate([_FakeAttrRow(**self.ledger)])
        if "GROUP BY" in sql:
            return _FakeAggregate(
                [_FakeAttrRow(reason=k, total=v) for k, v in self.blocked.items()]
            )
        if "count(" in sql:
            self.delivered_since.append(
                next(
                    (v for v in compiled.params.values() if hasattr(v, "tzinfo")),
                    None,
                )
            )
            if isinstance(self.delivered, list):
                return _FakeAggregate([], scalar=self.delivered.pop(0))
            return _FakeAggregate([], scalar=self.delivered)
        raise AssertionError(f"FakeMetricsSession saw an unmodelled statement: {sql}")

    async def commit(self) -> None:  # pragma: no cover — must never be called
        self.commits += 1


class _FakeAttrRow:
    def __init__(self, **fields) -> None:
        self.__dict__.update(fields)


class _FakeAggregate:
    def __init__(self, rows, scalar=None) -> None:
        self._rows = rows
        self._scalar = scalar

    def all(self):
        return self._rows

    def one(self):
        return self._rows[0]

    def scalar(self):
        return self._scalar


class FakePipeline:
    """Stands in for the process-wide :class:`IntentPipeline`.

    The real one reaches the LLM classifier, so every Zalo dispatch test
    swaps it out. Records the text it was asked to classify — used to
    assert the classifier is *not* consulted twice, and never for logging.
    """

    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.texts: list[str] = []

    async def classify(self, text: str):
        self.texts.append(text)
        if self.error is not None:
            raise self.error
        return self.result


class FakeDispatcher:
    """Stands in for :class:`IntentDispatcher`.

    ``calls`` is the assertion that matters most: an intent outside the
    thin slice must leave this list empty, because dispatching one could
    have side effects (a wizard, a persisted pending action) that Zalo
    has no way to finish.
    """

    def __init__(self, outcome=None, error: Exception | None = None) -> None:
        self.outcome = outcome
        self.error = error
        self.calls: list[tuple] = []

    async def dispatch(self, result, user, db):
        self.calls.append((result, user, db))
        if self.error is not None:
            raise self.error
        return self.outcome


@pytest.fixture()
def install_intent_stack(monkeypatch):
    """Swap the shared classifier + dispatcher the Zalo handler borrows.

    The handler imports them lazily from
    :mod:`backend.bot.handlers.free_form_text` at call time, so patching
    the module attributes is enough — no import-order dance. Imported
    inside the fixture rather than at module scope so the phase-5.0 suites
    that never touch the intent stack don't pay to build it.

    Returns an installer: ``install_intent_stack(intent=..., outcome=...)``
    → ``(pipeline, dispatcher)``.
    """
    from backend.bot.handlers import free_form_text
    from backend.intent.dispatcher import OUTCOME_EXECUTED, DispatchOutcome
    from backend.intent.intents import CLASSIFIER_RULE, IntentResult, IntentType

    _UNSET = object()

    def _install(
        *,
        intent=IntentType.ACTION_QUICK_TRANSACTION,
        confidence: float = 0.95,
        result=_UNSET,
        outcome=_UNSET,
        classify_error: Exception | None = None,
        dispatch_error: Exception | None = None,
    ):
        if result is _UNSET:
            result = IntentResult(
                intent=intent,
                confidence=confidence,
                raw_text="",
                classifier_used=CLASSIFIER_RULE,
            )
        if outcome is _UNSET:
            outcome = DispatchOutcome(
                text="Đã ghi 50,000đ · Ăn uống",
                kind=OUTCOME_EXECUTED,
                intent=result.intent,
                confidence=result.confidence,
            )
        pipeline = FakePipeline(result, classify_error)
        dispatcher = FakeDispatcher(outcome, dispatch_error)
        monkeypatch.setattr(free_form_text, "get_pipeline", lambda: pipeline)
        monkeypatch.setattr(free_form_text, "get_dispatcher", lambda: dispatcher)
        return pipeline, dispatcher

    return _install
