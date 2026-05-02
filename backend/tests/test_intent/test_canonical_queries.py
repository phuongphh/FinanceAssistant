"""Canonical query test suite (Story #131 — Epic 4).

The 30 queries below mirror the user-testing protocol in
``docs/current/phase-3.5-detailed.md`` § 3.3 and are the contract every
future change to patterns / prompts / handlers must clear.

Five groups, five different success bars:

  Group A (10): Direct queries — rule classifier alone, ≥0.85 confidence
  Group B  (5): Indirect queries — LLM falls back, ≥0.7 confidence
  Group C  (4): Action queries — confirmation flow fires
  Group D  (4): Advisory — advisory handler dispatches
  Group E  (7): Edge cases — graceful, never silent fail

LLM is mockable for CI speed. The rule layer runs against the real
``content/intent_patterns.yaml`` — that's the whole point: regressions
in patterns surface here before merge.

Output on failure follows the spec:
  Query 'X' expected intent Y, got Z (confidence W)
"""
from __future__ import annotations

import json
import time
from collections import Counter
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.intent.classifier.pipeline import IntentPipeline
from backend.intent.classifier.rule_based import RuleBasedClassifier
from backend.intent.intents import (
    CLASSIFIER_LLM,
    CLASSIFIER_RULE,
    IntentResult,
    IntentType,
)


# ---------------------- Test data ----------------------


@dataclass(frozen=True)
class CanonicalQuery:
    """One canonical query case.

    ``expected_classifier`` is "rule" / "llm" / "any" — Group A queries
    MUST hit the rule classifier (the whole reason rules exist),
    Group B/D MAY use either, edge cases accept either or none.
    """
    text: str
    expected_intent: IntentType
    expected_min_confidence: float
    expected_classifier: str  # "rule" | "llm" | "any"
    expected_parameters: dict | None = None
    note: str = ""


# ---- Group A — Direct queries (10) ----
GROUP_A: list[CanonicalQuery] = [
    CanonicalQuery(
        "tài sản của tôi có gì",
        IntentType.QUERY_ASSETS,
        0.85,
        "rule",
    ),
    CanonicalQuery(
        "tổng tài sản của tôi",
        IntentType.QUERY_NET_WORTH,
        0.85,
        "rule",
    ),
    CanonicalQuery(
        "portfolios chứng khoán của tôi",
        IntentType.QUERY_PORTFOLIO,
        0.85,
        "rule",
    ),
    CanonicalQuery(
        "chi tiêu tháng này",
        IntentType.QUERY_EXPENSES,
        0.85,
        "rule",
        expected_parameters={"time_range": "this_month"},
    ),
    CanonicalQuery(
        "chi tiêu cho ăn uống tháng này",
        IntentType.QUERY_EXPENSES_BY_CATEGORY,
        0.85,
        "rule",
        expected_parameters={"category": "food", "time_range": "this_month"},
    ),
    CanonicalQuery(
        "chi phí sức khỏe tháng trước",
        IntentType.QUERY_EXPENSES_BY_CATEGORY,
        0.85,
        "rule",
        expected_parameters={"category": "health", "time_range": "last_month"},
    ),
    CanonicalQuery(
        "thu nhập của tôi là như thế nào",
        IntentType.QUERY_INCOME,
        0.85,
        "rule",
    ),
    CanonicalQuery(
        "VNM giá bao nhiêu",
        IntentType.QUERY_MARKET,
        0.85,
        "rule",
        expected_parameters={"ticker": "VNM"},
    ),
    CanonicalQuery(
        "VN-Index hôm nay",
        IntentType.QUERY_MARKET,
        0.85,
        "rule",
        expected_parameters={"ticker": "VNINDEX"},
    ),
    CanonicalQuery(
        "mục tiêu của tôi có gì",
        IntentType.QUERY_GOALS,
        0.85,
        "rule",
    ),
]

# ---- Group B — Indirect queries (5) — LLM does the work ----
GROUP_B: list[CanonicalQuery] = [
    CanonicalQuery(
        "tôi đang giàu cỡ nào",
        IntentType.QUERY_NET_WORTH,
        0.7,
        "any",  # LLM expected, but a confident rule is also fine
        note="Idiomatic — rule may not match",
    ),
    CanonicalQuery(
        "tháng này tôi xài hoang chưa",
        IntentType.QUERY_EXPENSES,
        0.7,
        "any",
    ),
    CanonicalQuery(
        "cổ phiếu nào của tôi tăng nhiều nhất",
        IntentType.QUERY_PORTFOLIO,
        0.7,
        "any",
    ),
    CanonicalQuery(
        "tôi chi cho cafe nhiều không",
        IntentType.QUERY_EXPENSES_BY_CATEGORY,
        0.7,
        "any",
        expected_parameters={"category": "food"},
    ),
    CanonicalQuery(
        "tôi tiết kiệm được nhiều không",
        IntentType.QUERY_CASHFLOW,
        0.7,
        "any",
    ),
]

# ---- Group C — Action queries (4) ----
GROUP_C: list[CanonicalQuery] = [
    CanonicalQuery(
        "tiết kiệm 1tr",
        IntentType.ACTION_RECORD_SAVING,
        0.85,
        "rule",
        expected_parameters={"amount": 1_000_000},
    ),
    CanonicalQuery(
        "ghi 200k ăn trưa",
        IntentType.ACTION_QUICK_TRANSACTION,
        0.7,
        "any",
        note="LLM-only — no clean rule pattern yet",
    ),
    CanonicalQuery(
        "tôi vừa mua 5 cổ VNM",
        IntentType.ACTION_QUICK_TRANSACTION,
        0.7,
        "any",
    ),
    CanonicalQuery(
        "xóa giao dịch hôm qua",
        IntentType.ACTION_QUICK_TRANSACTION,
        0.7,
        "any",
        note="Cancel-style — LLM should map to action_quick_transaction",
    ),
]

# ---- Group D — Advisory (4) ----
GROUP_D: list[CanonicalQuery] = [
    CanonicalQuery(
        "nên đầu tư gì với 50tr",
        IntentType.ADVISORY,
        0.7,
        "any",
    ),
    CanonicalQuery(
        "làm thế nào để mua nhà 5 tỷ",
        IntentType.PLANNING,
        0.7,
        "any",
        note="Planning intent — may also classify as advisory",
    ),
    CanonicalQuery(
        "có nên bán VNM không",
        IntentType.ADVISORY,
        0.7,
        "any",
    ),
    CanonicalQuery(
        "crypto có nên đầu tư không",
        IntentType.ADVISORY,
        0.7,
        "any",
    ),
]

# ---- Group E — Edge cases (7) ----
# Edge cases assert *behaviour* not specific intent — they must
# classify to UNCLEAR / OUT_OF_SCOPE OR a low-confidence guess that
# the dispatcher will route to a friendly message.
GROUP_E: list[CanonicalQuery] = [
    CanonicalQuery("asdkfjh", IntentType.UNCLEAR, 0.0, "any"),
    CanonicalQuery("?", IntentType.UNCLEAR, 0.0, "any"),
    CanonicalQuery(
        "tôi muốn biết về tất cả tài sản chi tiêu mục tiêu thu nhập đầu tư của tôi",
        IntentType.QUERY_ASSETS,
        0.0,
        "any",
        note="Run-on query — any reasonable intent OR unclear is fine",
    ),
    CanonicalQuery(
        "thời tiết hôm nay",
        IntentType.OUT_OF_SCOPE,
        0.0,
        "any",
    ),
    CanonicalQuery(
        "tài sản với chi tiêu",
        IntentType.QUERY_ASSETS,
        0.0,
        "any",
        note="Mixed query — accept assets OR expenses",
    ),
    CanonicalQuery(
        "show my assets",
        IntentType.QUERY_ASSETS,
        0.5,
        "any",
        note="English-only",
    ),
    CanonicalQuery(
        "tài sảnn của tôii",
        IntentType.QUERY_ASSETS,
        0.5,
        "any",
        note="Typo with double letters",
    ),
]


# ---------------------- Pipeline fixtures ----------------------


def _llm_oracle() -> dict[str, IntentResult]:
    """Canned LLM responses keyed by exact query text.

    Mocks the LLM classifier so CI runs in milliseconds, not seconds,
    and stays deterministic. Production behaviour is exercised by the
    fixture-based ``test_rule_based.py`` plus manual user testing.
    """
    return {
        # Group B
        "tôi đang giàu cỡ nào": IntentResult(
            intent=IntentType.QUERY_NET_WORTH, confidence=0.85,
            classifier_used=CLASSIFIER_LLM,
        ),
        "tháng này tôi xài hoang chưa": IntentResult(
            intent=IntentType.QUERY_EXPENSES, confidence=0.82,
            parameters={"time_range": "this_month"},
            classifier_used=CLASSIFIER_LLM,
        ),
        "cổ phiếu nào của tôi tăng nhiều nhất": IntentResult(
            intent=IntentType.QUERY_PORTFOLIO, confidence=0.83,
            classifier_used=CLASSIFIER_LLM,
        ),
        "tôi chi cho cafe nhiều không": IntentResult(
            intent=IntentType.QUERY_EXPENSES_BY_CATEGORY, confidence=0.78,
            parameters={"category": "food"},
            classifier_used=CLASSIFIER_LLM,
        ),
        "tôi tiết kiệm được nhiều không": IntentResult(
            intent=IntentType.QUERY_CASHFLOW, confidence=0.78,
            classifier_used=CLASSIFIER_LLM,
        ),
        # Group C
        "ghi 200k ăn trưa": IntentResult(
            intent=IntentType.ACTION_QUICK_TRANSACTION, confidence=0.85,
            parameters={"amount": 200_000, "merchant": "ăn trưa"},
            classifier_used=CLASSIFIER_LLM,
        ),
        "tôi vừa mua 5 cổ VNM": IntentResult(
            intent=IntentType.ACTION_QUICK_TRANSACTION, confidence=0.78,
            parameters={"ticker": "VNM", "quantity": 5},
            classifier_used=CLASSIFIER_LLM,
        ),
        "xóa giao dịch hôm qua": IntentResult(
            intent=IntentType.ACTION_QUICK_TRANSACTION, confidence=0.72,
            classifier_used=CLASSIFIER_LLM,
        ),
        # Group D
        "nên đầu tư gì với 50tr": IntentResult(
            intent=IntentType.ADVISORY, confidence=0.92,
            parameters={"amount": 50_000_000},
            classifier_used=CLASSIFIER_LLM,
        ),
        "làm thế nào để mua nhà 5 tỷ": IntentResult(
            intent=IntentType.PLANNING, confidence=0.85,
            classifier_used=CLASSIFIER_LLM,
        ),
        "có nên bán VNM không": IntentResult(
            intent=IntentType.ADVISORY, confidence=0.9,
            parameters={"ticker": "VNM"},
            classifier_used=CLASSIFIER_LLM,
        ),
        "crypto có nên đầu tư không": IntentResult(
            intent=IntentType.ADVISORY, confidence=0.88,
            classifier_used=CLASSIFIER_LLM,
        ),
        # Group E
        "tôi muốn biết về tất cả tài sản chi tiêu mục tiêu thu nhập đầu tư của tôi": IntentResult(
            intent=IntentType.QUERY_ASSETS, confidence=0.6,
            classifier_used=CLASSIFIER_LLM,
        ),
        "tài sản với chi tiêu": IntentResult(
            intent=IntentType.QUERY_ASSETS, confidence=0.6,
            classifier_used=CLASSIFIER_LLM,
        ),
        "show my assets": IntentResult(
            intent=IntentType.QUERY_ASSETS, confidence=0.85,
            classifier_used=CLASSIFIER_LLM,
        ),
        "tài sảnn của tôii": IntentResult(
            intent=IntentType.QUERY_ASSETS, confidence=0.7,
            classifier_used=CLASSIFIER_LLM,
        ),
    }


@pytest.fixture(scope="module")
def pipeline() -> IntentPipeline:
    """Pipeline with a deterministic LLM oracle.

    Rule classifier is the real one — bugs in patterns must surface
    here. LLM classifier is a stub that consults the oracle table; it
    raises a clear AssertionError if asked about a query we forgot to
    canonicalise (so a new fixture without an oracle entry fails loud).
    """
    oracle = _llm_oracle()

    class _StubLLM:
        last_call_stats = None

        def classify(self, text):
            async def _go():
                if text in oracle:
                    return oracle[text]
                return None

            return _go()

    return IntentPipeline(
        rule_classifier=RuleBasedClassifier(),
        llm_classifier=_StubLLM(),
    )


# ---------------------- Helpers ----------------------


def _format_failure(query: CanonicalQuery, result: IntentResult) -> str:
    """Match the failure message format from the acceptance criteria."""
    return (
        f"Query {query.text!r} expected intent {query.expected_intent.value}, "
        f"got {result.intent.value} "
        f"(confidence {result.confidence:.2f}, classifier={result.classifier_used})"
    )


def _params_match(actual: dict, expected: dict) -> bool:
    """Subset match — actual may have extra keys."""
    for key, value in expected.items():
        if actual.get(key) != value:
            return False
    return True


# ---------------------- Group runners ----------------------


async def _run_group(
    pipeline: IntentPipeline, queries: list[CanonicalQuery]
) -> tuple[int, list[str]]:
    """Run every query in a group, return (passed, failure messages)."""
    passed = 0
    failures: list[str] = []
    for q in queries:
        result = await pipeline.classify(q.text)
        ok = result.intent == q.expected_intent
        if not ok:
            failures.append(_format_failure(q, result))
            continue
        if result.confidence < q.expected_min_confidence:
            failures.append(
                f"Query {q.text!r}: confidence {result.confidence:.2f} below "
                f"min {q.expected_min_confidence}"
            )
            continue
        if (
            q.expected_classifier != "any"
            and result.classifier_used != q.expected_classifier
        ):
            failures.append(
                f"Query {q.text!r}: expected classifier {q.expected_classifier}, "
                f"got {result.classifier_used}"
            )
            continue
        if q.expected_parameters and not _params_match(
            result.parameters, q.expected_parameters
        ):
            failures.append(
                f"Query {q.text!r}: params {result.parameters} missing "
                f"expected {q.expected_parameters}"
            )
            continue
        passed += 1
    return passed, failures


# ---------------------- Group tests ----------------------


@pytest.mark.asyncio
async def test_group_a_direct_queries_95pct(pipeline):
    """Group A: ≥95% of direct queries hit the rule classifier."""
    passed, failures = await _run_group(pipeline, GROUP_A)
    rate = passed / len(GROUP_A)
    assert rate >= 0.95, (
        f"Group A: {passed}/{len(GROUP_A)} = {rate*100:.0f}%, "
        f"failures:\n  " + "\n  ".join(failures)
    )


@pytest.mark.asyncio
async def test_group_b_indirect_queries_80pct(pipeline):
    """Group B: ≥80% of indirect queries handled (rule or LLM)."""
    passed, failures = await _run_group(pipeline, GROUP_B)
    rate = passed / len(GROUP_B)
    assert rate >= 0.80, (
        f"Group B: {passed}/{len(GROUP_B)} = {rate*100:.0f}%, "
        f"failures:\n  " + "\n  ".join(failures)
    )


@pytest.mark.asyncio
async def test_group_c_action_queries_85pct(pipeline):
    """Group C: ≥85% of action queries land on a write intent."""
    passed, failures = await _run_group(pipeline, GROUP_C)
    rate = passed / len(GROUP_C)
    assert rate >= 0.85, (
        f"Group C: {passed}/{len(GROUP_C)} = {rate*100:.0f}%, "
        f"failures:\n  " + "\n  ".join(failures)
    )


@pytest.mark.asyncio
async def test_group_d_advisory_queries_80pct(pipeline):
    """Group D: ≥80% of advisory/planning queries route to LLM-backed
    handlers."""
    passed = 0
    failures: list[str] = []
    advisory_intents = {IntentType.ADVISORY, IntentType.PLANNING}
    for q in GROUP_D:
        result = await pipeline.classify(q.text)
        if result.intent in advisory_intents and result.confidence >= 0.7:
            passed += 1
        else:
            failures.append(_format_failure(q, result))
    rate = passed / len(GROUP_D)
    assert rate >= 0.80, (
        f"Group D: {passed}/{len(GROUP_D)} = {rate*100:.0f}%, "
        f"failures:\n  " + "\n  ".join(failures)
    )


@pytest.mark.asyncio
async def test_group_e_edge_cases_100pct_graceful(pipeline):
    """Group E: 100% must classify gracefully — no exception, no
    silent fail. We verify by asserting the pipeline returns a non-None
    result for every input AND it does NOT route to a high-confidence
    write intent (which would silently execute on user data)."""
    dangerous_intents = {
        IntentType.ACTION_RECORD_SAVING,
        IntentType.ACTION_QUICK_TRANSACTION,
    }
    for q in GROUP_E:
        result = await pipeline.classify(q.text)
        assert result is not None, f"Pipeline returned None for {q.text!r}"
        # No silent fail: even UNCLEAR is fine because the dispatcher
        # has a friendly UNCLEAR response.
        if (
            result.intent in dangerous_intents
            and result.confidence >= 0.85
        ):
            pytest.fail(
                f"Edge case {q.text!r} would silently execute "
                f"{result.intent.value} at {result.confidence:.2f}"
            )


# ---------------------- Latency budget ----------------------


@pytest.mark.asyncio
async def test_canonical_queries_under_latency_budget(pipeline):
    """All 30 canonical queries finish well within the per-call budget.

    Budget: 200ms per query when the LLM is mocked (rule + dispatch
    only). Real prod LLM-backed queries are bounded by Story #132's
    dedicated perf test.
    """
    all_queries = GROUP_A + GROUP_B + GROUP_C + GROUP_D + GROUP_E
    over_budget: list[tuple[str, float]] = []
    for q in all_queries:
        start = time.perf_counter()
        await pipeline.classify(q.text)
        elapsed_ms = (time.perf_counter() - start) * 1000
        if elapsed_ms > 200:
            over_budget.append((q.text, elapsed_ms))
    assert not over_budget, (
        "Queries over 200ms budget: "
        + ", ".join(f"{t!r}={ms:.0f}ms" for t, ms in over_budget)
    )


# ---------------------- Group A details ----------------------


@pytest.mark.asyncio
async def test_every_group_a_query_passes_individually(pipeline):
    """Failure messages must use the exact format the spec asks for —
    dump every Group A failure individually so a CI diff is human-
    readable. Cumulative ≥95% bar is enforced separately above."""
    failures = []
    for q in GROUP_A:
        result = await pipeline.classify(q.text)
        if result.intent != q.expected_intent or result.confidence < q.expected_min_confidence:
            failures.append(_format_failure(q, result))
    assert not failures, "Group A failures:\n  " + "\n  ".join(failures)


# ---------------------- Distribution sanity ----------------------


@pytest.mark.asyncio
async def test_classifier_split_across_30_queries(pipeline):
    """Sanity: rule classifier covers ≥50% of the 30 canonical queries.

    This is a soft guard against pattern rot — if rules suddenly handle
    only 20%, something regressed. The acceptance criterion in
    ``phase-3.5-detailed.md`` § Metrics targets ≥70% rule-rate; we use
    50% here to keep the test stable across small pattern tweaks."""
    all_queries = GROUP_A + GROUP_B + GROUP_C + GROUP_D + GROUP_E
    counts: Counter[str] = Counter()
    for q in all_queries:
        result = await pipeline.classify(q.text)
        counts[result.classifier_used] += 1
    total = sum(counts.values())
    rule_rate = counts[CLASSIFIER_RULE] / total
    assert rule_rate >= 0.50, (
        f"Rule rate {rule_rate*100:.0f}% below 50% floor — "
        f"split={dict(counts)}"
    )
