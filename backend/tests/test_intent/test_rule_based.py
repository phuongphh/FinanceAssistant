"""End-to-end tests for the rule-based classifier against the shared
fixture set."""
from __future__ import annotations

import time
from collections import Counter

import pytest

from backend.intent.classifier.rule_based import RuleBasedClassifier
from backend.intent.intents import IntentType
from backend.tests.test_intent.fixtures import load_query_fixtures


@pytest.fixture(scope="module")
def classifier() -> RuleBasedClassifier:
    return RuleBasedClassifier()


# ---------------------- canonical fixtures ----------------------


@pytest.mark.parametrize(
    "fixture", load_query_fixtures("canonical"), ids=lambda f: f.text
)
def test_canonical_queries_classify_correctly(fixture, classifier):
    result = classifier.classify(fixture.text)
    assert result is not None, (
        f"No match for canonical query: {fixture.text!r} ({fixture.notes})"
    )
    assert result.intent.value == fixture.expected_intent, (
        f"{fixture.text!r}: expected {fixture.expected_intent}, "
        f"got {result.intent.value}"
    )
    assert result.confidence >= fixture.expected_min_confidence, (
        f"{fixture.text!r}: confidence {result.confidence} below "
        f"minimum {fixture.expected_min_confidence}"
    )
    for key, expected in fixture.expected_parameters.items():
        actual = result.parameters.get(key)
        assert actual == expected, (
            f"{fixture.text!r}: param {key!r} expected {expected!r}, "
            f"got {actual!r}"
        )


# ---------------------- edge cases ----------------------


@pytest.mark.parametrize(
    "fixture", load_query_fixtures("edge_cases"), ids=lambda f: f.text
)
def test_edge_cases_handled_gracefully(fixture, classifier):
    """Edge cases must EITHER classify to the expected intent (above
    relaxed confidence) OR return None — they must NEVER mis-classify
    to a confidence-≥0.85 wrong intent (which would silently execute)."""
    result = classifier.classify(fixture.text)

    if fixture.expected_intent in ("unclear", "out_of_scope"):
        # Acceptable outcomes: result is None OR result intent matches.
        if result is None:
            return
        assert result.intent.value == fixture.expected_intent or (
            result.confidence < 0.85
        ), (
            f"{fixture.text!r}: expected unclear/OOS but got "
            f"{result.intent.value} at {result.confidence}"
        )
        return

    # Otherwise we want the right intent at the relaxed confidence bar.
    assert result is not None, f"No match for {fixture.text!r}"
    assert result.intent.value == fixture.expected_intent, (
        f"{fixture.text!r}: expected {fixture.expected_intent}, "
        f"got {result.intent.value}"
    )
    assert result.confidence >= fixture.expected_min_confidence


# ---------------------- correctness invariants ----------------------


def test_out_of_scope_never_returns_a_query_intent(classifier):
    oos_inputs = [
        "thời tiết hôm nay thế nào",
        "tỷ giá USD/VND",  # Not a Phase 3.5 supported query.
        "1 + 1 = ?",
    ]
    for text in oos_inputs:
        result = classifier.classify(text)
        if result is None:
            continue
        # If we matched anything, it shouldn't be a high-confidence
        # query/action intent — those would silently execute against
        # the user's data.
        bad = {
            IntentType.QUERY_ASSETS,
            IntentType.QUERY_NET_WORTH,
            IntentType.ACTION_RECORD_SAVING,
            IntentType.ACTION_QUICK_TRANSACTION,
        }
        assert not (
            result.intent in bad and result.confidence >= 0.85
        ), f"{text!r}: would execute {result.intent.value} at {result.confidence}"


def test_canonical_fixtures_cover_all_intent_groups(classifier):
    """Smoke test that the fixture file actually exercises a mix of
    intents — cheap insurance against accidentally narrowing the YAML."""
    counts: Counter[str] = Counter()
    for fix in load_query_fixtures("canonical"):
        result = classifier.classify(fix.text)
        if result is not None:
            counts[result.intent.value] += 1

    # At least 6 distinct intents should appear among the canonical
    # set (we ship with ~10).
    assert len(counts) >= 6, f"Too few intents covered: {counts}"


# ---------------------- performance ----------------------


def test_100_queries_under_5_seconds(classifier):
    """Latency budget — the rule path must stay sub-50ms / query."""
    sample = [f.text for f in load_query_fixtures()] * 4  # ≥ 100
    sample = sample[:100]
    start = time.perf_counter()
    for text in sample:
        classifier.classify(text)
    elapsed = time.perf_counter() - start
    assert elapsed < 5.0, f"100 classifications took {elapsed:.2f}s"
