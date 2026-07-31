"""Phase 4.5 / E3 / Issue #3.1 — clarity_service.score_clarity() unit tests.

The scoring core is pure, so these tests fabricate ``ClarityInputs`` directly
— no database, no clock — and assert the two properties the Epic requires:

1. Four representative profiles (empty / asset-only / asset+income / full)
   produce sensibly increasing scores.
2. Adding *any* data never lowers the score (monotonicity).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from backend.services.decision.clarity_service import (
    CLARITY_MIN_THRESHOLD,
    COMPONENT_WEIGHTS,
    ClarityInputs,
    score_clarity,
)

NOW = datetime(2026, 7, 10, tzinfo=timezone.utc)


def _inputs(**overrides) -> ClarityInputs:
    base = dict(
        active_asset_count=0,
        distinct_asset_types=0,
        latest_asset_valued_at=None,
        income_source_count=0,
        expense_month_count=0,
        active_goal_count=0,
        now=NOW,
    )
    base.update(overrides)
    return ClarityInputs(**base)


EMPTY = _inputs()
ASSET_ONLY = _inputs(
    active_asset_count=2,
    distinct_asset_types=2,
    latest_asset_valued_at=NOW - timedelta(days=5),
)
ASSET_INCOME = _inputs(
    active_asset_count=2,
    distinct_asset_types=2,
    latest_asset_valued_at=NOW - timedelta(days=5),
    income_source_count=1,
)
FULL = _inputs(
    active_asset_count=4,
    distinct_asset_types=3,
    latest_asset_valued_at=NOW - timedelta(days=2),
    income_source_count=2,
    expense_month_count=3,
    active_goal_count=2,
)


def test_weights_sum_to_100():
    assert sum(COMPONENT_WEIGHTS.values()) == 100


def test_empty_profile_scores_zero():
    result = score_clarity(EMPTY)
    assert result.score == 0
    assert result.is_below_threshold
    # Every component is missing; humble mode points at the heaviest one.
    top = result.top_missing()
    assert top is not None
    assert top.key == "assets"  # 30 is the max weight


def test_full_profile_scores_100():
    result = score_clarity(FULL)
    assert result.score == 100
    assert not result.is_below_threshold
    # Nothing left to sharpen.
    assert result.top_sharpen() is None
    assert result.top_missing() is None


def test_profiles_increase_monotonically():
    scores = [
        score_clarity(EMPTY).score,
        score_clarity(ASSET_ONLY).score,
        score_clarity(ASSET_INCOME).score,
        score_clarity(FULL).score,
    ]
    assert scores == sorted(scores)
    # And each step is a *strict* increase — every profile adds real data.
    assert scores[0] < scores[1] < scores[2] < scores[3]


def test_asset_only_crosses_threshold_but_not_full():
    result = score_clarity(ASSET_ONLY)
    assert 0 < result.score < 100
    # income/expenses/goals are all still missing.
    missing_keys = {c.key for c in result.components if c.is_missing}
    assert missing_keys == {"income", "expenses", "goals"}


@pytest.mark.parametrize(
    "field,low,high",
    [
        ("active_asset_count", 0, 1),
        ("distinct_asset_types", 1, 3),
        ("income_source_count", 1, 2),
        ("expense_month_count", 1, 3),
        ("active_goal_count", 1, 2),
    ],
)
def test_adding_data_never_lowers_score(field, low, high):
    # Start from a mid-rich profile so every field has room to move.
    base = _inputs(
        active_asset_count=1,
        distinct_asset_types=1,
        latest_asset_valued_at=NOW - timedelta(days=10),
        income_source_count=1,
        expense_month_count=1,
        active_goal_count=1,
    )
    lower = score_clarity(_replace(base, field, low)).score
    higher = score_clarity(_replace(base, field, high)).score
    assert higher >= lower


def test_fresher_assets_never_lower_score():
    stale = _inputs(
        active_asset_count=1,
        distinct_asset_types=1,
        latest_asset_valued_at=NOW - timedelta(days=200),
    )
    fresh = _inputs(
        active_asset_count=1,
        distinct_asset_types=1,
        latest_asset_valued_at=NOW - timedelta(days=1),
    )
    assert score_clarity(fresh).score >= score_clarity(stale).score


def test_component_earned_never_exceeds_weight():
    result = score_clarity(FULL)
    for component in result.components:
        assert Decimal("0") <= component.earned <= component.weight


def test_threshold_constant_is_reasonable():
    assert 0 < CLARITY_MIN_THRESHOLD < 100


def _replace(inputs: ClarityInputs, field: str, value) -> ClarityInputs:
    data = {
        "active_asset_count": inputs.active_asset_count,
        "distinct_asset_types": inputs.distinct_asset_types,
        "latest_asset_valued_at": inputs.latest_asset_valued_at,
        "income_source_count": inputs.income_source_count,
        "expense_month_count": inputs.expense_month_count,
        "active_goal_count": inputs.active_goal_count,
        "now": inputs.now,
    }
    data[field] = value
    return ClarityInputs(**data)
