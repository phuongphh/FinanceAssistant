"""Phase 4.5 / E1 / Issue #1.3 — DecisionShockHandler wiring.

The handler is the flag-gated edge in front of the pure ``simulate_shock`` +
``rank_options`` + formatter:

* Flag dark → delegate to the generic ``AdvisoryHandler`` unchanged.
* Flag on, missing amount → exactly one warm clarify question.
* Flag on, empty portfolio → warm "chưa có tài sản" copy (no crash).
* Flag on, shock > 50% of net worth, unconfirmed → a one-line confirm gate;
  with ``shock_confirmed`` it proceeds to the full scenario.
* Flag on, full params → weather verdict + redraw plan, and when the clarity
  meter is on the độ nét block is appended.

The one DB call (``load_portfolio_snapshot``) is monkeypatched so these stay
DB-free and fast.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.intent.handlers import advisory as advisory_mod
from backend.intent.handlers import decision_shock as dsh
from backend.intent.handlers.decision_shock import (
    DecisionShockHandler,
    _coerce_amount,
    _is_confirmed,
)
from backend.intent.intents import IntentResult, IntentType
from backend.twin.services.twin_projection_service import PortfolioSnapshot
from tests.test_phase_4_5.conftest import FakeSession

FLAG = "SHOCK_SIMULATION_ENABLED"
CLARITY_FLAG = "CLARITY_METER_ENABLED"
_BANNED = ("Decision Engine", "CFO", "GPS")


def _intent(**params) -> IntentResult:
    return IntentResult(
        intent=IntentType.DECISION_SHOCK,
        confidence=0.8,
        parameters=dict(params),
        raw_text="nếu phải chi 200tr thì sao",
    )


def _user():
    return SimpleNamespace(id=uuid.uuid4(), salutation="bạn")


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


def _patch_snapshot(monkeypatch, snap):
    async def fake_load(db, user_id):
        return snap

    monkeypatch.setattr(dsh, "load_portfolio_snapshot", fake_load)


# --------------------------------------------------------------------------
# Flag gating
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flag_off_delegates_to_advisory(monkeypatch):
    monkeypatch.delenv(FLAG, raising=False)

    seen = {}

    class FakeAdvisory:
        async def handle(self, intent, user, db):
            seen["called"] = True
            return "ADVISORY_FALLBACK"

    monkeypatch.setattr(advisory_mod, "AdvisoryHandler", FakeAdvisory)

    out = await DecisionShockHandler().handle(
        _intent(shock_amount=200_000_000), _user(), None
    )
    assert out == "ADVISORY_FALLBACK"
    assert seen.get("called") is True


@pytest.mark.asyncio
async def test_flag_on_missing_amount_clarifies(monkeypatch):
    monkeypatch.setenv(FLAG, "true")
    out = await DecisionShockHandler().handle(_intent(), _user(), FakeSession())
    assert "bao nhiêu" in out


@pytest.mark.asyncio
async def test_flag_on_empty_portfolio(monkeypatch):
    monkeypatch.setenv(FLAG, "true")
    _patch_snapshot(
        monkeypatch,
        PortfolioSnapshot(
            base_net_worth=Decimal(0),
            monthly_savings=Decimal(0),
            allocation_amounts={},
            allocation_weights={},
        ),
    )
    out = await DecisionShockHandler().handle(
        _intent(shock_amount=200_000_000), _user(), FakeSession()
    )
    assert "chưa" in out
    for banned in _BANNED:
        assert banned not in out


# --------------------------------------------------------------------------
# Confirm gate
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_large_shock_asks_confirm_first(monkeypatch):
    monkeypatch.setenv(FLAG, "true")
    monkeypatch.delenv(CLARITY_FLAG, raising=False)
    _patch_snapshot(monkeypatch, _snapshot())

    # 700tr > 50% of 1 tỷ net worth → confirm gate fires, sim never runs.
    def _boom(*a, **k):  # pragma: no cover - must not be called
        raise AssertionError("simulate_shock ran before confirm")

    monkeypatch.setattr(dsh, "simulate_shock", _boom)

    out = await DecisionShockHandler().handle(
        _intent(shock_amount=700_000_000), _user(), FakeSession()
    )
    assert "khá lớn" in out


@pytest.mark.asyncio
async def test_large_shock_proceeds_when_confirmed(monkeypatch):
    monkeypatch.setenv(FLAG, "true")
    monkeypatch.delenv(CLARITY_FLAG, raising=False)
    _patch_snapshot(monkeypatch, _snapshot())

    out = await DecisionShockHandler().handle(
        _intent(shock_amount=700_000_000, shock_confirmed=True), _user(), FakeSession()
    )
    # Full scenario rendered — weather + redraw, not the confirm question.
    assert "khá lớn" not in out
    assert out
    for banned in _BANNED:
        assert banned not in out


# --------------------------------------------------------------------------
# Full render + clarity surfacing
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_render_without_clarity(monkeypatch):
    monkeypatch.setenv(FLAG, "true")
    monkeypatch.delenv(CLARITY_FLAG, raising=False)
    _patch_snapshot(monkeypatch, _snapshot())

    out = await DecisionShockHandler().handle(
        _intent(shock_amount=200_000_000), _user(), FakeSession()
    )
    assert out
    # Redraw list names owned classes.
    assert "tiền gửi" in out
    for banned in _BANNED:
        assert banned not in out


@pytest.mark.asyncio
async def test_full_render_appends_clarity_block(monkeypatch):
    monkeypatch.setenv(FLAG, "true")
    monkeypatch.setenv(CLARITY_FLAG, "true")
    _patch_snapshot(monkeypatch, _snapshot())

    async def fake_clarity(db, user_id):
        return SimpleNamespace(
            score=62,
            is_below_threshold=False,
            top_sharpen=lambda: None,
            top_missing=lambda: None,
        )

    monkeypatch.setattr(dsh.clarity_service, "compute_clarity", fake_clarity)

    out = await DecisionShockHandler().handle(
        _intent(shock_amount=200_000_000), _user(), FakeSession()
    )
    assert "62%" in out  # clarity headline appended


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


@pytest.mark.parametrize("value", [None, True, False, 0, -5, "abc", "", "  "])
def test_coerce_amount_rejects_junk(value):
    assert _coerce_amount(value) is None


@pytest.mark.parametrize(
    "value,expected",
    [
        ("yes", True),
        ("có", True),
        (True, True),
        ("ok", True),
        (None, False),
        ("no", False),
        ("", False),
        (False, False),
    ],
)
def test_is_confirmed(value, expected):
    assert _is_confirmed({"shock_confirmed": value}) is expected
