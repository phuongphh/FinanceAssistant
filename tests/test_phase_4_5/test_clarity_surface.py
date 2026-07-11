"""Phase 4.5 / E3 / Issues #3.2–#3.4 — surfacing the Độ Nét meter.

These cover the pure, DB-free pieces of surfacing clarity:

* #3.2 — ``to_payload`` shape (Twin Mini App/API) and ``render_clarity_line``.
* #3.3 — humble mode below the threshold names the missing component;
  above the threshold offers exactly one sharpen nudge.
* #3.4 — the ``CLARITY_METER_ENABLED`` flag helper defaults off and honours
  the usual truthy/falsy spellings.

The scoring core is pure, so we fabricate ``ClarityInputs`` and score them
directly — no database, no clock.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.bot.formatters import clarity as clarity_fmt
from backend.intent.handlers import decision_flags
from backend.services.decision.clarity_service import (
    CLARITY_MIN_THRESHOLD,
    ClarityInputs,
    score_clarity,
    to_payload,
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
FULL = _inputs(
    active_asset_count=4,
    distinct_asset_types=3,
    latest_asset_valued_at=NOW - timedelta(days=2),
    income_source_count=2,
    expense_month_count=3,
    active_goal_count=2,
)


# --------------------------------------------------------------------------
# #3.2 — payload + line
# --------------------------------------------------------------------------


def test_to_payload_shape_full():
    payload = to_payload(score_clarity(FULL))
    assert payload["score"] == 100
    assert payload["threshold"] == CLARITY_MIN_THRESHOLD
    assert payload["below_threshold"] is False
    assert payload["top_missing"] is None
    assert payload["top_sharpen"] is None
    keys = {c["key"] for c in payload["components"]}
    assert keys == {"assets", "asset_freshness", "income", "expenses", "goals"}
    for comp in payload["components"]:
        # earned is a float for the front-end, never a Decimal.
        assert isinstance(comp["earned"], float)
        assert 0.0 <= comp["earned"] <= comp["weight"]
        assert isinstance(comp["complete"], bool)


def test_to_payload_shape_empty():
    payload = to_payload(score_clarity(EMPTY))
    assert payload["score"] == 0
    assert payload["below_threshold"] is True
    assert payload["top_missing"] == "assets"  # heaviest missing component
    assert payload["top_sharpen"] == "assets"


def test_render_line_contains_score():
    line = clarity_fmt.render_clarity_line(score_clarity(FULL))
    assert "100" in line
    # No forbidden internal jargon leaks into user-facing copy.
    for banned in ("Decision Engine", "CFO", "GPS"):
        assert banned not in line


# --------------------------------------------------------------------------
# #3.3 — humble mode vs sharpen nudge
# --------------------------------------------------------------------------


def test_below_threshold_is_humble_and_names_missing():
    result = score_clarity(EMPTY)
    assert result.is_below_threshold
    block = clarity_fmt.render_clarity_block(result)
    # Humble intro present, and the heaviest missing component is named.
    assert "mờ" in block
    assert "thông tin tài sản" in block  # label for "assets"
    # Multi-line: headline + humble intro + suggest.
    assert block.count("\n") >= 2


def test_above_threshold_offers_single_sharpen():
    # Assets only: crosses the threshold but income/expenses/goals missing.
    result = score_clarity(
        _inputs(
            active_asset_count=2,
            distinct_asset_types=2,
            latest_asset_valued_at=NOW - timedelta(days=3),
        )
    )
    assert not result.is_below_threshold
    block = clarity_fmt.render_clarity_block(result)
    lines = block.split("\n")
    # Exactly one nudge beyond the headline.
    assert len(lines) == 2
    assert "nét hơn" in lines[1]


def test_full_profile_block_is_headline_only():
    block = clarity_fmt.render_clarity_block(score_clarity(FULL))
    assert "\n" not in block  # nothing left to sharpen


# --------------------------------------------------------------------------
# #3.4 — feature flag
# --------------------------------------------------------------------------


def test_flag_defaults_off(monkeypatch):
    monkeypatch.delenv(decision_flags.CLARITY_METER_ENABLED_ENV, raising=False)
    assert decision_flags.is_clarity_meter_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_flag_on(monkeypatch, value):
    monkeypatch.setenv(decision_flags.CLARITY_METER_ENABLED_ENV, value)
    assert decision_flags.is_clarity_meter_enabled() is True


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "", "garbage"])
def test_flag_off(monkeypatch, value):
    monkeypatch.setenv(decision_flags.CLARITY_METER_ENABLED_ENV, value)
    assert decision_flags.is_clarity_meter_enabled() is False
