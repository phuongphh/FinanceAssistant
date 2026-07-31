"""Phase 4.6 / E4 / Issue #4.1 — cohort tag on the decision query log.

The append-only ``decision_query_logs`` rows now carry an onboarding cohort so
the admin dashboard can split the new first-life segment (22-35, Level 0→1)
from the legacy asset-management cohort. Three layers under test:

* ``cohort_for_goal`` — the pure classifier (reset / legacy / None).
* ``cohort_service.resolve_user_cohort`` — the one-lookup resolver used by the
  shock + feasibility handlers, which only carry a ``user_id``.
* ``log_query`` + the two handlers — the ``cohort`` is threaded onto the row,
  and an untagged user still logs (cohort ``None``), never crashing.

All DB-free: the shared ``FakeSession`` records added rows and stubs the single
``db.scalar`` cohort lookup.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend import models
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
from backend.models.onboarding_session import (
    COHORT_LEGACY,
    COHORT_RESET,
    GOAL_EMERGENCY_FUND,
    GOAL_FIRST_HOME,
    GOAL_PLAN_GOAL,
    GOAL_TRACK_SPENDING,
    GOAL_UNDERSTAND_WEALTH,
    GOAL_WEDDING,
    LEGACY_GOALS,
    RESET_GOALS,
    cohort_for_goal,
)
from backend.services.decision import cohort_service
from backend.services.decision import decision_query_log_service as log_svc
from backend.twin.services.twin_projection_service import PortfolioSnapshot
from tests.test_phase_4_5.conftest import FakeSession

SHOCK_FLAG = "SHOCK_SIMULATION_ENABLED"
FEAS_FLAG = "PLAN_FEASIBILITY_QA_ENABLED"
CLARITY_FLAG = "CLARITY_METER_ENABLED"


def _user():
    return SimpleNamespace(id=uuid.uuid4(), salutation="bạn")


def _logged_rows(db: FakeSession) -> list[DecisionQueryLog]:
    return [r for r in db.added if isinstance(r, DecisionQueryLog)]


# --------------------------------------------------------------------------
# The pure classifier
# --------------------------------------------------------------------------


@pytest.mark.parametrize("goal", RESET_GOALS)
def test_reset_goals_map_to_reset_cohort(goal):
    assert cohort_for_goal(goal) == COHORT_RESET


@pytest.mark.parametrize("goal", LEGACY_GOALS)
def test_legacy_goals_map_to_legacy_cohort(goal):
    assert cohort_for_goal(goal) == COHORT_LEGACY


@pytest.mark.parametrize("goal", [None, "", "some_unknown_goal", "RESET"])
def test_unknown_or_missing_goal_is_untagged(goal):
    assert cohort_for_goal(goal) is None


def test_cohorts_are_disjoint_and_reset_covers_new_segment():
    # Every first-life goal is reset, every asset-management goal is legacy,
    # and the two sets never overlap — no goal is ambiguously bucketed.
    assert {cohort_for_goal(g) for g in RESET_GOALS} == {COHORT_RESET}
    assert {cohort_for_goal(g) for g in LEGACY_GOALS} == {COHORT_LEGACY}
    assert set(RESET_GOALS).isdisjoint(LEGACY_GOALS)


def test_cohort_codes_fit_the_column():
    # decision_query_logs.cohort is String(16).
    assert len(COHORT_RESET) <= 16
    assert len(COHORT_LEGACY) <= 16


def test_reexported_from_models_package():
    assert models.cohort_for_goal is cohort_for_goal
    assert models.COHORT_RESET == COHORT_RESET
    assert models.COHORT_LEGACY == COHORT_LEGACY


# --------------------------------------------------------------------------
# The one-lookup resolver
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("goal", "expected"),
    [
        (GOAL_EMERGENCY_FUND, COHORT_RESET),
        (GOAL_FIRST_HOME, COHORT_RESET),
        (GOAL_WEDDING, COHORT_RESET),
        (GOAL_UNDERSTAND_WEALTH, COHORT_LEGACY),
        (GOAL_PLAN_GOAL, COHORT_LEGACY),
        (GOAL_TRACK_SPENDING, COHORT_LEGACY),
        (None, None),
    ],
)
async def test_resolve_user_cohort(goal, expected):
    db = FakeSession(goal_choice=goal)
    assert await cohort_service.resolve_user_cohort(db, uuid.uuid4()) == expected


# --------------------------------------------------------------------------
# The flush-only writer
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_query_persists_cohort():
    db = FakeSession()
    row = await log_svc.log_query(
        db,
        user_id=uuid.uuid4(),
        query_type=QUERY_TYPE_SHOCK,
        success=True,
        cohort=COHORT_RESET,
    )
    assert row.cohort == COHORT_RESET
    assert db.flushes == 1


@pytest.mark.asyncio
async def test_log_query_cohort_defaults_to_none():
    db = FakeSession()
    row = await log_svc.log_query(
        db, user_id=uuid.uuid4(), query_type=QUERY_TYPE_FEASIBILITY, success=False
    )
    assert row.cohort is None


# --------------------------------------------------------------------------
# Handler threading — the cohort lands on the logged row
# --------------------------------------------------------------------------


def _shock_intent(**params) -> IntentResult:
    return IntentResult(
        intent=IntentType.DECISION_SHOCK,
        confidence=0.8,
        parameters=dict(params),
        raw_text="nếu phải chi 200tr thì sao",
    )


def _feas_intent(**params) -> IntentResult:
    return IntentResult(
        intent=IntentType.DECISION_FEASIBILITY,
        confidence=0.8,
        parameters=dict(params),
        raw_text="muốn có 1 tỷ sau 5 năm khả thi không",
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


@pytest.mark.asyncio
async def test_shock_tags_row_with_reset_cohort(monkeypatch):
    monkeypatch.setenv(SHOCK_FLAG, "true")
    monkeypatch.delenv(CLARITY_FLAG, raising=False)

    async def fake_load(db, user_id):
        return _snapshot()

    monkeypatch.setattr(dsh, "load_portfolio_snapshot", fake_load)
    # A reset-goal user asking a shock question → row.cohort == "reset".
    db = FakeSession(goal_choice=GOAL_FIRST_HOME)
    await DecisionShockHandler().handle(
        _shock_intent(shock_amount=200_000_000), _user(), db
    )
    rows = _logged_rows(db)
    assert len(rows) == 1
    assert rows[0].cohort == COHORT_RESET


@pytest.mark.asyncio
async def test_shock_untagged_user_logs_with_none_cohort(monkeypatch):
    monkeypatch.setenv(SHOCK_FLAG, "true")
    db = FakeSession()  # no onboarding goal → untagged, still logs
    await DecisionShockHandler().handle(_shock_intent(), _user(), db)
    rows = _logged_rows(db)
    assert len(rows) == 1
    assert rows[0].cohort is None


@pytest.mark.asyncio
async def test_feasibility_tags_row_with_legacy_cohort(monkeypatch):
    monkeypatch.setenv(FEAS_FLAG, "true")

    async def fake_savings(db, user_id, *, today=None):
        return Decimal(5_000_000)

    monkeypatch.setattr(dfh, "get_avg_monthly_savings", fake_savings)
    db = FakeSession(goal_choice=GOAL_UNDERSTAND_WEALTH)
    await DecisionFeasibilityHandler().handle(
        _feas_intent(target_amount=60_000_000, horizon_years=5), _user(), db
    )
    rows = _logged_rows(db)
    assert len(rows) == 1
    assert rows[0].cohort == COHORT_LEGACY
