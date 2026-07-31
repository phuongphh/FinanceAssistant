"""Phase 4.5 / E5 / Issue #5.1 — Decision query log.

Every handled Decision-Engine question drops one append-only row — including
the clarify / empty / confirm turns that never reach a verdict, which land as
``success=False`` so the Phase 4.6 funnel shows where users stall.

Two layers under test:

* ``decision_query_log_service.log_query`` — the flush-only writer. It must
  ``add`` + ``flush`` and **never commit** (layer contract), and coerce an int
  score to ``Decimal``.
* The E1 (shock) and E2 (feasibility) handlers — each logs exactly once per
  handled call with the right ``query_type`` / ``success`` / ``clarity_score``,
  and logs *nothing* on the flag-dark advisory-fallback path.

All DB-free: a ``FakeSession`` records what was added and the one real DB read
in each handler is monkeypatched.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.intent.handlers import advisory as advisory_mod
from backend.intent.handlers import decision_feasibility as dfh
from backend.intent.handlers import decision_shock as dsh
from backend.intent.handlers.decision_feasibility import DecisionFeasibilityHandler
from backend.intent.handlers.decision_shock import DecisionShockHandler
from backend.intent.intents import IntentResult, IntentType
from backend.models.decision_query_log import (
    QUERY_TYPE_FEASIBILITY,
    QUERY_TYPE_SHOCK,
    DecisionQueryLog,
)
from backend.services.decision import decision_query_log_service as log_svc
from backend.twin.services.twin_projection_service import PortfolioSnapshot
from tests.test_phase_4_5.conftest import FakeSession

SHOCK_FLAG = "SHOCK_SIMULATION_ENABLED"
FEAS_FLAG = "PLAN_FEASIBILITY_QA_ENABLED"
CLARITY_FLAG = "CLARITY_METER_ENABLED"


def _user():
    return SimpleNamespace(id=uuid.uuid4(), salutation="bạn")


# --------------------------------------------------------------------------
# The flush-only writer
# --------------------------------------------------------------------------


class _CommitTrap(FakeSession):
    """A session that fails the test if anyone tries to commit — the service
    layer must flush only; the worker owns the transaction boundary."""

    async def commit(self):  # pragma: no cover - must never be called
        raise AssertionError("service layer must not commit")


@pytest.mark.asyncio
async def test_log_query_adds_and_flushes_without_commit():
    db = _CommitTrap()
    uid = uuid.uuid4()
    row = await log_svc.log_query(
        db, user_id=uid, query_type=QUERY_TYPE_SHOCK, success=True, clarity_score=62
    )
    assert isinstance(row, DecisionQueryLog)
    assert db.added == [row]
    assert db.flushes == 1
    assert row.user_id == uid
    assert row.query_type == QUERY_TYPE_SHOCK
    assert row.success is True
    # int score coerced to Decimal so callers can pass ClarityResult.score.
    assert row.clarity_score == Decimal(62)
    assert isinstance(row.clarity_score, Decimal)


@pytest.mark.asyncio
async def test_log_query_success_false_and_null_score():
    db = FakeSession()
    row = await log_svc.log_query(
        db, user_id=uuid.uuid4(), query_type=QUERY_TYPE_FEASIBILITY, success=False
    )
    assert row.success is False
    assert row.clarity_score is None
    assert db.flushes == 1


@pytest.mark.asyncio
async def test_log_query_accepts_decimal_score():
    db = FakeSession()
    row = await log_svc.log_query(
        db,
        user_id=uuid.uuid4(),
        query_type=QUERY_TYPE_SHOCK,
        success=True,
        clarity_score=Decimal("48.5"),
    )
    assert row.clarity_score == Decimal("48.5")


# --------------------------------------------------------------------------
# Shock handler logging
# --------------------------------------------------------------------------


def _shock_intent(**params) -> IntentResult:
    return IntentResult(
        intent=IntentType.DECISION_SHOCK,
        confidence=0.8,
        parameters=dict(params),
        raw_text="nếu phải chi 200tr thì sao",
    )


def _snapshot(net_worth: Decimal = Decimal(1_000_000_000)) -> PortfolioSnapshot:
    amounts = {
        "cash_savings": net_worth * Decimal("0.3"),
        "stocks_vn": net_worth * Decimal("0.4"),
        "gold": net_worth * Decimal("0.3"),
    }
    total = sum(amounts.values(), Decimal(0))
    return PortfolioSnapshot(
        base_net_worth=net_worth,
        monthly_savings=Decimal(5_000_000),
        allocation_amounts=amounts,
        allocation_weights={k: v / total for k, v in amounts.items()},
    )


def _logged_rows(db: FakeSession) -> list[DecisionQueryLog]:
    return [r for r in db.added if isinstance(r, DecisionQueryLog)]


@pytest.mark.asyncio
async def test_shock_flag_off_logs_nothing(monkeypatch):
    monkeypatch.delenv(SHOCK_FLAG, raising=False)

    class FakeAdvisory:
        async def handle(self, intent, user, db):
            return "ADVISORY_FALLBACK"

    monkeypatch.setattr(advisory_mod, "AdvisoryHandler", FakeAdvisory)

    db = FakeSession()
    out = await DecisionShockHandler().handle(
        _shock_intent(shock_amount=200_000_000), _user(), db
    )
    assert out == "ADVISORY_FALLBACK"
    assert _logged_rows(db) == []  # dark surface → no decision query counted


@pytest.mark.asyncio
async def test_shock_missing_amount_logs_failure(monkeypatch):
    monkeypatch.setenv(SHOCK_FLAG, "true")
    db = FakeSession()
    await DecisionShockHandler().handle(_shock_intent(), _user(), db)
    rows = _logged_rows(db)
    assert len(rows) == 1
    assert rows[0].query_type == QUERY_TYPE_SHOCK
    assert rows[0].success is False
    assert rows[0].clarity_score is None


@pytest.mark.asyncio
async def test_shock_empty_portfolio_logs_failure(monkeypatch):
    monkeypatch.setenv(SHOCK_FLAG, "true")

    async def fake_load(db, user_id):
        return PortfolioSnapshot(
            base_net_worth=Decimal(0),
            monthly_savings=Decimal(0),
            allocation_amounts={},
            allocation_weights={},
        )

    monkeypatch.setattr(dsh, "load_portfolio_snapshot", fake_load)
    db = FakeSession()
    await DecisionShockHandler().handle(
        _shock_intent(shock_amount=200_000_000), _user(), db
    )
    rows = _logged_rows(db)
    assert len(rows) == 1 and rows[0].success is False


@pytest.mark.asyncio
async def test_shock_confirm_gate_logs_failure(monkeypatch):
    monkeypatch.setenv(SHOCK_FLAG, "true")
    monkeypatch.delenv(CLARITY_FLAG, raising=False)

    async def fake_load(db, user_id):
        return _snapshot()

    monkeypatch.setattr(dsh, "load_portfolio_snapshot", fake_load)
    db = FakeSession()
    # 700tr > 50% of 1 tỷ → confirm gate, no verdict → success=False.
    await DecisionShockHandler().handle(
        _shock_intent(shock_amount=700_000_000), _user(), db
    )
    rows = _logged_rows(db)
    assert len(rows) == 1 and rows[0].success is False


@pytest.mark.asyncio
async def test_shock_full_verdict_logs_success_without_clarity(monkeypatch):
    monkeypatch.setenv(SHOCK_FLAG, "true")
    monkeypatch.delenv(CLARITY_FLAG, raising=False)

    async def fake_load(db, user_id):
        return _snapshot()

    monkeypatch.setattr(dsh, "load_portfolio_snapshot", fake_load)
    db = FakeSession()
    await DecisionShockHandler().handle(
        _shock_intent(shock_amount=200_000_000), _user(), db
    )
    rows = _logged_rows(db)
    assert len(rows) == 1
    assert rows[0].success is True
    assert rows[0].clarity_score is None  # meter off → no score


@pytest.mark.asyncio
async def test_shock_full_verdict_logs_clarity_score(monkeypatch):
    monkeypatch.setenv(SHOCK_FLAG, "true")
    monkeypatch.setenv(CLARITY_FLAG, "true")

    async def fake_load(db, user_id):
        return _snapshot()

    async def fake_clarity(db, user_id):
        return SimpleNamespace(
            score=62,
            is_below_threshold=False,
            top_sharpen=lambda: None,
            top_missing=lambda: None,
        )

    monkeypatch.setattr(dsh, "load_portfolio_snapshot", fake_load)
    monkeypatch.setattr(dsh.clarity_service, "compute_clarity", fake_clarity)
    db = FakeSession()
    await DecisionShockHandler().handle(
        _shock_intent(shock_amount=200_000_000), _user(), db
    )
    rows = _logged_rows(db)
    assert len(rows) == 1
    assert rows[0].success is True
    assert rows[0].clarity_score == Decimal(62)  # độ nét captured on the row


# --------------------------------------------------------------------------
# Feasibility handler logging
# --------------------------------------------------------------------------


def _feas_intent(**params) -> IntentResult:
    return IntentResult(
        intent=IntentType.DECISION_FEASIBILITY,
        confidence=0.8,
        parameters=dict(params),
        raw_text="muốn có 1 tỷ sau 5 năm khả thi không",
    )


@pytest.mark.asyncio
async def test_feasibility_flag_off_logs_nothing(monkeypatch):
    monkeypatch.delenv(FEAS_FLAG, raising=False)

    class FakeAdvisory:
        async def handle(self, intent, user, db):
            return "ADVISORY_FALLBACK"

    monkeypatch.setattr(advisory_mod, "AdvisoryHandler", FakeAdvisory)
    db = FakeSession()
    out = await DecisionFeasibilityHandler().handle(
        _feas_intent(target_amount=1_000_000_000, horizon_years=5), _user(), db
    )
    assert out == "ADVISORY_FALLBACK"
    assert _logged_rows(db) == []


@pytest.mark.asyncio
async def test_feasibility_missing_target_logs_failure(monkeypatch):
    monkeypatch.setenv(FEAS_FLAG, "true")
    db = FakeSession()
    await DecisionFeasibilityHandler().handle(
        _feas_intent(horizon_years=5), _user(), db
    )
    rows = _logged_rows(db)
    assert len(rows) == 1
    assert rows[0].query_type == QUERY_TYPE_FEASIBILITY
    assert rows[0].success is False


@pytest.mark.asyncio
async def test_feasibility_full_verdict_logs_success(monkeypatch):
    monkeypatch.setenv(FEAS_FLAG, "true")

    async def fake_savings(db, user_id, *, today=None):
        return Decimal(5_000_000)

    monkeypatch.setattr(dfh, "get_avg_monthly_savings", fake_savings)
    db = FakeSession()
    await DecisionFeasibilityHandler().handle(
        _feas_intent(target_amount=60_000_000, horizon_years=5), _user(), db
    )
    rows = _logged_rows(db)
    assert len(rows) == 1
    assert rows[0].query_type == QUERY_TYPE_FEASIBILITY
    assert rows[0].success is True
    # Feasibility does not surface độ nét → no score on the row.
    assert rows[0].clarity_score is None


@pytest.mark.asyncio
async def test_handlers_log_exactly_once_per_call(monkeypatch):
    """Guard against double-logging: a single handled call = one row."""
    monkeypatch.setenv(SHOCK_FLAG, "true")
    monkeypatch.delenv(CLARITY_FLAG, raising=False)

    async def fake_load(db, user_id):
        return _snapshot()

    monkeypatch.setattr(dsh, "load_portfolio_snapshot", fake_load)
    db = FakeSession()
    await DecisionShockHandler().handle(
        _shock_intent(shock_amount=200_000_000), _user(), db
    )
    assert len(_logged_rows(db)) == 1
    assert db.flushes == 1
