"""Tests for the IntentType enum + IntentResult dataclass."""
from __future__ import annotations

import json

from backend.intent.intents import (
    CLASSIFIER_RULE,
    IntentResult,
    IntentType,
)


class TestIntentType:
    def test_str_enum_values(self):
        # str-Enum membership lets analytics serialise the value as plain
        # text and YAML fixtures match by string equality.
        assert IntentType.QUERY_ASSETS.value == "query_assets"
        assert IntentType("query_assets") is IntentType.QUERY_ASSETS

    def test_covers_all_phase_3_5_intents(self):
        names = {i.value for i in IntentType}
        # 17 intents per acceptance criteria of issue #114.
        expected = {
            "query_assets", "query_net_worth", "query_portfolio",
            "query_expenses", "query_expenses_by_category",
            "query_income", "query_cashflow",
            "query_market", "query_goals", "query_goal_progress",
            "action_record_saving", "action_quick_transaction",
            "advisory", "planning",
            "greeting", "help", "unclear", "out_of_scope",
        }
        assert expected.issubset(names)


class TestIntentResult:
    def test_default_parameters_independent_per_instance(self):
        a = IntentResult(intent=IntentType.UNCLEAR, confidence=0.0)
        b = IntentResult(intent=IntentType.UNCLEAR, confidence=0.0)
        a.parameters["x"] = 1
        # If parameters was a shared mutable default, mutating ``a``
        # would leak into ``b`` — the field(default_factory=dict)
        # idiom prevents that.
        assert b.parameters == {}

    def test_to_dict_round_trips_via_json(self):
        result = IntentResult(
            intent=IntentType.QUERY_MARKET,
            confidence=0.92,
            parameters={"ticker": "VNM"},
            raw_text="VNM giá bao nhiêu?",
            classifier_used=CLASSIFIER_RULE,
        )
        as_json = json.dumps(result.to_dict())
        loaded = json.loads(as_json)
        assert loaded["intent"] == "query_market"
        assert loaded["confidence"] == 0.92
        assert loaded["parameters"] == {"ticker": "VNM"}
        assert loaded["classifier_used"] == "rule"
