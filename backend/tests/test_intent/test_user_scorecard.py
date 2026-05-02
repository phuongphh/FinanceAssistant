"""Tests for the user-testing scorecard generator (Story #133)."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.scripts.intent_user_scorecard import collect, print_scorecard


def _result_with_rows(rows):
    res = MagicMock()
    res.all.return_value = rows
    return res


def _result_with_scalar(value):
    res = MagicMock()
    res.scalar.return_value = value
    return res


def _row(event_type: str, count: int) -> MagicMock:
    """Stand-in for the (event_type, count) tuple from .all()."""
    return (event_type, count)


def _classifier_row(name: str, count: int) -> MagicMock:
    return (name, count)


def _fake_session_factory(execute_side_effect):
    db = MagicMock()
    db.execute = AsyncMock(side_effect=execute_side_effect)

    class _Factory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return db

        async def __aexit__(self, *exc):
            return False

    return _Factory()


@pytest.mark.asyncio
async def test_collect_aggregates_event_counts_and_rates():
    """Counts roll up to the rate formulas the scorecard uses."""
    side_effects = [
        # 1. event_type counts
        _result_with_rows([
            _row("intent_classified", 50),
            _row("intent_handler_executed", 38),
            _row("intent_unclear", 8),
            _row("morning_briefing_sent", 7),
            _row("morning_briefing_opened", 5),
            _row("advisory_response_sent", 3),
            _row("voice_query_received", 4),
            _row("intent_confirm_sent", 6),
            _row("intent_confirm_accepted", 5),
            _row("intent_confirm_rejected", 1),
            _row("intent_followup_tapped", 12),
        ]),
        # 2. avg latency
        _result_with_scalar(120.5),
        # 3. classifier split
        _result_with_rows([
            _classifier_row("rule", 35),
            _classifier_row("llm", 12),
            _classifier_row("none", 3),
        ]),
    ]

    factory = _fake_session_factory(side_effects)
    with patch(
        "backend.database.get_session_factory",
        lambda: factory,
    ):
        sc = await collect(uuid.uuid4(), days=7)

    assert sc["total_classified"] == 50
    assert sc["rule_rate"] == 0.7  # 35 / 50
    assert sc["unclear_rate"] == 0.16  # 8 / 50
    assert sc["execution_rate"] == 0.76  # 38 / 50
    assert sc["briefing_open_rate"] == round(5 / 7, 4)
    assert sc["avg_latency_ms"] == 120.5
    assert sc["advisory_count"] == 3
    assert sc["voice_count"] == 4
    assert sc["confirm_accepted"] == 5
    assert sc["confirm_rejected"] == 1


@pytest.mark.asyncio
async def test_collect_handles_zero_events_without_divide_by_zero():
    """A user with no activity should produce a scorecard, not crash."""
    side_effects = [
        _result_with_rows([]),
        _result_with_scalar(None),
        _result_with_rows([]),
    ]
    factory = _fake_session_factory(side_effects)
    with patch(
        "backend.database.get_session_factory",
        lambda: factory,
    ):
        sc = await collect(uuid.uuid4(), days=7)

    assert sc["total_classified"] == 0
    assert sc["rule_rate"] == 0.0
    assert sc["unclear_rate"] == 0.0
    assert sc["briefing_open_rate"] == 0.0
    assert sc["avg_latency_ms"] == 0.0


def test_print_scorecard_emits_required_lines(capsys):
    """The printed output must include the labels the protocol doc
    references — auditors copy / paste into the spreadsheet."""
    scorecard = {
        "user_id": "00000000-0000-0000-0000-000000000001",
        "window_days": 7,
        "total_classified": 50,
        "by_classifier": {"rule": 35, "llm": 12, "none": 3},
        "rule_rate": 0.7,
        "unclear_rate": 0.16,
        "execution_rate": 0.76,
        "briefing_open_rate": 5 / 7,
        "avg_latency_ms": 120.5,
        "advisory_count": 3,
        "advisory_rate_limited": 0,
        "voice_count": 4,
        "voice_failed": 0,
        "confirm_sent": 6,
        "confirm_accepted": 5,
        "confirm_rejected": 1,
        "followup_tapped": 12,
        "raw_counts": {},
    }
    print_scorecard(scorecard)
    out = capsys.readouterr().out
    for label in [
        "Total queries",
        "Rule classifier rate",
        "Unclear rate",
        "Briefing open rate",
        "Avg response latency",
        "Confirm rejected",
    ]:
        assert label in out
