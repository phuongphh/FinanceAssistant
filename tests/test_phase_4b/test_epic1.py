"""Phase 4B Epic 1 tests — S1 accuracy, S2 recompute threshold, S5 uncertainty."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from backend.twin.accuracy import AccuracySummary, _extract_p50_at_year_0
from backend.twin.engine.uncertainty import UncertaintyContributor, compute_uncertainty_breakdown
from backend.twin.services import recompute_service


# ---------------------------------------------------------------------------
# S1 — Accuracy summary tone property
# ---------------------------------------------------------------------------


def make_summary(actual: Decimal, predicted: Decimal) -> AccuracySummary:
    error = (actual - predicted) / predicted * Decimal("100")
    return AccuracySummary(predicted_p50=predicted, actual=actual, error_pct=error)


def test_accuracy_tone_celebrate():
    s = make_summary(actual=Decimal("115000000"), predicted=Decimal("100000000"))
    assert s.tone == "celebrate"


def test_accuracy_tone_reassure():
    s = make_summary(actual=Decimal("85000000"), predicted=Decimal("100000000"))
    assert s.tone == "reassure"


def test_accuracy_tone_neutral_above():
    s = make_summary(actual=Decimal("108000000"), predicted=Decimal("100000000"))
    assert s.tone == "neutral"


def test_accuracy_tone_neutral_below():
    s = make_summary(actual=Decimal("92000000"), predicted=Decimal("100000000"))
    assert s.tone == "neutral"


def test_accuracy_tone_exact_boundary_celebrate():
    s = make_summary(actual=Decimal("110000001"), predicted=Decimal("100000000"))
    assert s.tone == "celebrate"


def test_accuracy_tone_exact_boundary_reassure():
    s = make_summary(actual=Decimal("89999999"), predicted=Decimal("100000000"))
    assert s.tone == "reassure"


def test_extract_p50_at_year_0_returns_year_zero():
    cone = [
        {"year": 0, "p10": "80000000", "p50": "100000000", "p90": "120000000"},
        {"year": 1, "p10": "82000000", "p50": "105000000", "p90": "128000000"},
    ]
    result = _extract_p50_at_year_0(cone)
    assert result == Decimal("100000000")


def test_extract_p50_at_year_0_fallback_to_first():
    cone = [{"year": 1, "p10": "80000000", "p50": "105000000", "p90": "120000000"}]
    result = _extract_p50_at_year_0(cone)
    assert result == Decimal("105000000")


def test_extract_p50_at_year_0_empty():
    assert _extract_p50_at_year_0([]) is None


# ---------------------------------------------------------------------------
# S1 — fill_previous_projection_accuracy with fake DB
# ---------------------------------------------------------------------------


class FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class FakeDB:
    def __init__(self, execute_returns: Any = None):
        self._execute_returns = execute_returns
        self.flush_count = 0

    async def execute(self, stmt):
        return FakeScalarResult(self._execute_returns)

    async def flush(self):
        self.flush_count += 1


@pytest.mark.asyncio
async def test_fill_accuracy_returns_false_when_no_unfilled_projection(monkeypatch):
    from backend.twin import accuracy

    db = FakeDB(execute_returns=None)
    result = await accuracy.fill_previous_projection_accuracy(db, uuid.uuid4())
    assert result is False
    assert db.flush_count == 0


@pytest.mark.asyncio
async def test_fill_accuracy_updates_and_flushes(monkeypatch):
    from backend.twin import accuracy

    proj = SimpleNamespace(
        id=uuid.uuid4(),
        actual_net_worth=None,
        computed_at=datetime.now(timezone.utc),
    )
    db = FakeDB(execute_returns=proj)

    async def fake_calculate(db_, uid):
        return SimpleNamespace(total=Decimal("110000000"))

    monkeypatch.setattr(accuracy.wealth_service, "calculate_stored_current", fake_calculate)

    result = await accuracy.fill_previous_projection_accuracy(db, uuid.uuid4())
    assert result is True
    assert proj.actual_net_worth == Decimal("110000000")
    assert db.flush_count == 1


@pytest.mark.asyncio
async def test_fill_accuracy_returns_false_on_wealth_service_error(monkeypatch):
    from backend.twin import accuracy

    proj = SimpleNamespace(
        id=uuid.uuid4(),
        actual_net_worth=None,
        computed_at=datetime.now(timezone.utc),
    )
    db = FakeDB(execute_returns=proj)

    async def raise_error(db_, uid):
        raise RuntimeError("DB unavailable")

    monkeypatch.setattr(accuracy.wealth_service, "calculate_stored_current", raise_error)

    result = await accuracy.fill_previous_projection_accuracy(db, uuid.uuid4())
    assert result is False
    assert db.flush_count == 0


# ---------------------------------------------------------------------------
# S1 — get_accuracy_summary with fake DB
# ---------------------------------------------------------------------------


class FakeScalarsResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class FakeDBMultiRow:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, stmt):
        return FakeScalarsResult(self._rows)


@pytest.mark.asyncio
async def test_get_accuracy_summary_none_with_one_projection():
    from backend.twin import accuracy

    rows = [
        SimpleNamespace(
            actual_net_worth=Decimal("100000000"),
            cone_data=[{"year": 0, "p50": "95000000"}],
        )
    ]
    db = FakeDBMultiRow(rows)
    result = await accuracy.get_accuracy_summary(db, uuid.uuid4())
    assert result is None  # needs ≥ 2 projections


@pytest.mark.asyncio
async def test_get_accuracy_summary_none_when_no_filled_projection():
    from backend.twin import accuracy

    rows = [
        SimpleNamespace(actual_net_worth=None, cone_data=[{"year": 0, "p50": "95000000"}]),
        SimpleNamespace(actual_net_worth=None, cone_data=[{"year": 0, "p50": "90000000"}]),
    ]
    db = FakeDBMultiRow(rows)
    result = await accuracy.get_accuracy_summary(db, uuid.uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_get_accuracy_summary_returns_summary_celebrate():
    from backend.twin import accuracy

    rows = [
        SimpleNamespace(
            actual_net_worth=Decimal("115000000"),
            cone_data=[{"year": 0, "p50": "100000000"}],
        ),
        SimpleNamespace(
            actual_net_worth=None,
            cone_data=[{"year": 0, "p50": "90000000"}],
        ),
    ]
    db = FakeDBMultiRow(rows)
    summary = await accuracy.get_accuracy_summary(db, uuid.uuid4())
    assert summary is not None
    assert summary.tone == "celebrate"
    assert summary.predicted_p50 == Decimal("100000000")
    assert summary.actual == Decimal("115000000")


# ---------------------------------------------------------------------------
# S2 — recompute threshold behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_should_recompute_below_threshold_returns_false(monkeypatch):
    user_id = uuid.uuid4()
    recompute_service._pending_user_ids.clear()

    async def fake_latest(db, uid, scenario=None):
        return None  # no prior projection — skip debounce check

    async def fake_current(db, uid):
        return SimpleNamespace(total=Decimal("100000000"))

    monkeypatch.setattr(recompute_service, "get_latest_projection", fake_latest)
    monkeypatch.setattr(recompute_service.wealth_service, "calculate_stored_current", fake_current)

    result = await recompute_service.should_recompute(
        object(), user_id, Decimal("4000000")  # 4% change, below 5% threshold
    )
    assert result is False


@pytest.mark.asyncio
async def test_should_recompute_at_threshold_returns_true(monkeypatch):
    user_id = uuid.uuid4()
    recompute_service._pending_user_ids.clear()

    async def fake_latest(db, uid, scenario=None):
        return None

    async def fake_current(db, uid):
        return SimpleNamespace(total=Decimal("100000000"))

    monkeypatch.setattr(recompute_service, "get_latest_projection", fake_latest)
    monkeypatch.setattr(recompute_service.wealth_service, "calculate_stored_current", fake_current)

    result = await recompute_service.should_recompute(
        object(), user_id, Decimal("5000000")  # exactly 5% threshold
    )
    assert result is True


@pytest.mark.asyncio
async def test_should_recompute_debounce_window_blocks(monkeypatch):
    """Debounce holds when the projection's base still matches the wallet
    — the user is editing inside a stable portfolio so we throttle.
    Divergent wallets are tested separately, since they intentionally
    bypass the long debounce."""
    user_id = uuid.uuid4()
    recompute_service._pending_user_ids.clear()

    fresh_projection = SimpleNamespace(
        computed_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        base_net_worth=Decimal("100000000"),
    )

    async def fake_latest(db, uid, scenario=None):
        return fresh_projection

    async def fake_current(db, uid):
        return SimpleNamespace(total=Decimal("100000000"))

    monkeypatch.setattr(recompute_service, "get_latest_projection", fake_latest)
    monkeypatch.setattr(recompute_service.wealth_service, "calculate_stored_current", fake_current)

    result = await recompute_service.should_recompute(
        object(), user_id, Decimal("10000000")  # 10% change but within debounce
    )
    assert result is False


@pytest.mark.asyncio
async def test_should_recompute_after_debounce_window(monkeypatch):
    user_id = uuid.uuid4()
    recompute_service._pending_user_ids.clear()

    stale_projection = SimpleNamespace(
        computed_at=datetime.now(timezone.utc) - timedelta(minutes=35)
    )

    async def fake_latest(db, uid, scenario=None):
        return stale_projection

    async def fake_current(db, uid):
        return SimpleNamespace(total=Decimal("100000000"))

    monkeypatch.setattr(recompute_service, "get_latest_projection", fake_latest)
    monkeypatch.setattr(recompute_service.wealth_service, "calculate_stored_current", fake_current)

    result = await recompute_service.should_recompute(
        object(), user_id, Decimal("10000000")  # 10% change, past debounce window
    )
    assert result is True


# ---------------------------------------------------------------------------
# S5 — uncertainty breakdown
# ---------------------------------------------------------------------------


def test_uncertainty_empty_allocation():
    result = compute_uncertainty_breakdown({})
    assert result == []


def test_uncertainty_single_asset():
    result = compute_uncertainty_breakdown({"stocks_vn": Decimal("100000000")})
    assert len(result) == 1
    assert result[0].asset_class == "stocks_vn"
    assert result[0].contribution_pct == pytest.approx(100.0, abs=0.1)


def test_uncertainty_high_sigma_dominates():
    allocation = {
        "crypto": Decimal("30000000"),   # high sigma ~0.80
        "bonds_vn": Decimal("70000000"),  # low sigma ~0.05
    }
    result = compute_uncertainty_breakdown(allocation, top_n=2)
    assert len(result) == 2
    # crypto has much higher sigma so should contribute more despite lower weight
    assert result[0].asset_class == "crypto"
    assert result[0].contribution_pct > result[1].contribution_pct


def test_uncertainty_top_n_limits_results():
    allocation = {
        "stocks_vn": Decimal("40000000"),
        "crypto": Decimal("20000000"),
        "gold": Decimal("20000000"),
        "cash_savings": Decimal("20000000"),
    }
    result = compute_uncertainty_breakdown(allocation, top_n=2)
    assert len(result) <= 2


def test_uncertainty_contributions_sum_to_roughly_100():
    allocation = {
        "stocks_vn": Decimal("50000000"),
        "cash_savings": Decimal("30000000"),
        "gold": Decimal("20000000"),
    }
    result = compute_uncertainty_breakdown(allocation, top_n=10)
    total = sum(c.contribution_pct for c in result)
    assert abs(total - 100.0) < 1.0  # rounding tolerance


def test_uncertainty_returns_dataclass():
    result = compute_uncertainty_breakdown({"stocks_vn": Decimal("100000000")})
    assert isinstance(result[0], UncertaintyContributor)
    assert hasattr(result[0], "asset_class")
    assert hasattr(result[0], "contribution_pct")


def test_uncertainty_zero_allocation_returns_empty():
    result = compute_uncertainty_breakdown({"stocks_vn": Decimal("0"), "gold": Decimal("0")})
    assert result == []
