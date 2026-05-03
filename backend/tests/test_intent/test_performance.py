"""Performance benchmarks for the intent layer (Story #132 — Epic 4).

Targets from ``docs/current/phase-3.5-detailed.md`` § Metrics:

  Rule classifier         p50 < 50ms,  p99 < 200ms
  End-to-end (text)       p50 < 1s,    p99 < 3s    [LLM mocked here]
  100 queries / 60 sec    no errors, no rate limiting

The LLM call itself is mocked because we don't want CI to depend on
DeepSeek availability. Real LLM latency is verified manually during
user testing (Story #133); this test guards the in-process budget so
we catch regressions in pattern compilation, dispatcher overhead, etc.

Each test prints percentiles via ``capsys`` so the perf-report doc
can lift the numbers verbatim.
"""
from __future__ import annotations

import asyncio
import statistics
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.intent.classifier.pipeline import IntentPipeline
from backend.intent.classifier.rule_based import RuleBasedClassifier
from backend.intent.intents import CLASSIFIER_LLM, IntentResult, IntentType


# Sample queries — mix that resembles real traffic. Some hit rule,
# some force LLM, some are unclear. Keep the list cheap to import.
_SAMPLE_QUERIES = [
    "tài sản của tôi có gì",
    "tổng tài sản của tôi",
    "portfolios chứng khoán của tôi",
    "chi tiêu tháng này",
    "chi tiêu cho ăn uống tháng này",
    "thu nhập của tôi",
    "VNM giá bao nhiêu",
    "VN-Index hôm nay",
    "mục tiêu của tôi",
    "tiết kiệm 1tr",
    "show my assets",
    "tai san cua toi",
    "bitcoin giá hôm nay",
    "tháng này tôi tiết kiệm được bao nhiêu",
    "asdkfjh",
    "thời tiết hôm nay",
    "chào",
    "/help",
    "tôi đang giàu cỡ nào",
    "có nên bán VNM không",
]


def _percentile(values: list[float], pct: float) -> float:
    """Linear-interpolation percentile so 1- and 2-sample inputs don't
    crash. Returns ms."""
    if not values:
        return 0.0
    values = sorted(values)
    k = (len(values) - 1) * (pct / 100)
    lower = int(k)
    upper = min(lower + 1, len(values) - 1)
    fraction = k - lower
    return values[lower] + (values[upper] - values[lower]) * fraction


# ---------------------- Rule classifier ----------------------


def test_rule_classifier_under_latency_budget(capsys):
    """p50 < 50ms, p99 < 200ms — single-call latency, no async overhead."""
    rc = RuleBasedClassifier()
    timings_ms: list[float] = []
    # Warm-up — the first call compiles regexes lazily.
    rc.classify("warm up")

    for _ in range(10):
        for q in _SAMPLE_QUERIES:
            start = time.perf_counter()
            rc.classify(q)
            timings_ms.append((time.perf_counter() - start) * 1000)

    p50 = _percentile(timings_ms, 50)
    p99 = _percentile(timings_ms, 99)
    capsys.disabled()  # let prints through
    print(
        f"\n[perf] rule classifier: n={len(timings_ms)} "
        f"p50={p50:.2f}ms p99={p99:.2f}ms max={max(timings_ms):.2f}ms"
    )
    assert p50 < 50, f"rule p50={p50:.1f}ms exceeds 50ms target"
    assert p99 < 200, f"rule p99={p99:.1f}ms exceeds 200ms target"


# ---------------------- End-to-end pipeline ----------------------


def _mock_llm() -> MagicMock:
    """Cheap LLM stub that returns immediately. Real DeepSeek latency
    is verified manually; this test cares about pipeline overhead."""
    llm = MagicMock()
    llm.last_call_stats = None

    async def _classify(text):
        return IntentResult(
            intent=IntentType.UNCLEAR,
            confidence=0.0,
            raw_text=text,
            classifier_used=CLASSIFIER_LLM,
        )

    llm.classify = _classify
    return llm


@pytest.mark.asyncio
async def test_pipeline_under_latency_budget(capsys):
    """End-to-end with mocked LLM: p50 < 1s, p99 < 3s.

    The async overhead alone should be ≤2-3ms; rule classifier adds
    ~5ms; the budget exists for production where the LLM dominates."""
    pipeline = IntentPipeline(
        rule_classifier=RuleBasedClassifier(),
        llm_classifier=_mock_llm(),
    )
    timings_ms: list[float] = []

    for _ in range(5):
        for q in _SAMPLE_QUERIES:
            start = time.perf_counter()
            await pipeline.classify(q)
            timings_ms.append((time.perf_counter() - start) * 1000)

    p50 = _percentile(timings_ms, 50)
    p99 = _percentile(timings_ms, 99)
    print(
        f"\n[perf] pipeline (mocked LLM): n={len(timings_ms)} "
        f"p50={p50:.2f}ms p99={p99:.2f}ms"
    )
    assert p50 < 1000, f"pipeline p50={p50:.1f}ms exceeds 1s target"
    assert p99 < 3000, f"pipeline p99={p99:.1f}ms exceeds 3s target"


# ---------------------- Load test ----------------------


@pytest.mark.asyncio
async def test_100_queries_in_60_seconds(capsys):
    """Load test: 100 queries in 60s, no errors, latency-bounded.

    Burst all 100 concurrently — closer to real Telegram traffic where
    multiple users tap buttons simultaneously than a serial loop."""
    pipeline = IntentPipeline(
        rule_classifier=RuleBasedClassifier(),
        llm_classifier=_mock_llm(),
    )
    queries = (_SAMPLE_QUERIES * 6)[:100]

    start = time.perf_counter()
    results = await asyncio.gather(
        *(pipeline.classify(q) for q in queries),
        return_exceptions=True,
    )
    elapsed_s = time.perf_counter() - start

    errors = [r for r in results if isinstance(r, Exception)]
    print(
        f"\n[perf] load test: 100 concurrent queries in {elapsed_s:.2f}s "
        f"(throughput={100/elapsed_s:.0f}/s, errors={len(errors)})"
    )
    assert not errors, f"{len(errors)} concurrent classifications errored: {errors[:3]}"
    assert elapsed_s < 60, f"100 concurrent queries took {elapsed_s:.1f}s — over 60s budget"


# ---------------------- Cost estimate ----------------------


def test_llm_cost_per_call_within_budget():
    """Acceptance: LLM cost per call < $0.0005.

    We synthesize a representative classify call by computing tokens
    against the prompt size and a typical short JSON response. The
    LLMClassifier owns the canonical cost calc — we replay it here so
    a price/token-per-char regression surfaces without needing a live
    API key.
    """
    from backend.intent.classifier.llm_based import LLMClassifier

    classifier = LLMClassifier()
    # Synthetic prompt + response sized like real calls observed in
    # dev: ~1100-char prompt (the LLM_CLASSIFIER_PROMPT body), ~80-char
    # response (one-line JSON).
    sample_prompt = "x" * 1100
    sample_response = '{"intent":"query_assets","confidence":0.92,"parameters":{}}'

    stats = classifier._build_stats(
        sample_prompt, sample_response, latency_ms=500, cache_hit=False
    )
    # Print so the perf doc can grab the figure.
    print(
        f"\n[perf] LLM cost/call: ${stats.cost_usd:.6f} "
        f"(input={stats.input_tokens}t, output={stats.output_tokens}t)"
    )
    assert stats.cost_usd < 0.0005, f"cost ${stats.cost_usd:.6f} exceeds budget"


def test_monthly_cost_projection_under_5_usd_at_1000_per_day():
    """Projection: 1000 queries/day → < $5/month.

    Mix assumed: 25% LLM-classified (per Tier C design), 5% advisory
    (with longer prompts). Cache hit rate assumed 30% on the
    classifier (same query asked twice).
    """
    from backend.intent.classifier.llm_based import LLMClassifier

    classifier = LLMClassifier()

    # Classifier call cost.
    sample_prompt = "x" * 1100
    sample_response = '{"intent":"query_assets","confidence":0.92,"parameters":{}}'
    classifier_cost = classifier._build_stats(
        sample_prompt, sample_response, latency_ms=500, cache_hit=False
    ).cost_usd

    # Advisory call cost — longer prompt, longer response.
    advisory_prompt = "x" * 1500
    advisory_response = "x" * 800  # ~200 word reply
    advisory_cost = classifier._build_stats(
        advisory_prompt, advisory_response, latency_ms=2000, cache_hit=False
    ).cost_usd

    queries_per_day = 1000
    llm_classifier_share = 0.25
    advisory_share = 0.05
    cache_hit_rate = 0.30

    daily_cost = (
        queries_per_day * llm_classifier_share * (1 - cache_hit_rate) * classifier_cost
        + queries_per_day * advisory_share * advisory_cost
    )
    monthly_cost = daily_cost * 30

    print(
        f"\n[perf] projected monthly cost @ 1000q/day: ${monthly_cost:.2f} "
        f"(classifier=${classifier_cost:.6f}/call, advisory=${advisory_cost:.6f}/call)"
    )
    assert monthly_cost < 5.0, (
        f"projected ${monthly_cost:.2f}/month exceeds $5 budget"
    )


def test_monthly_cost_projection_under_30_usd_at_10000_per_day():
    """Projection: 10000 queries/day → < $30/month.

    Same mix as above, just 10× volume. Linear in queries — if the
    1000/day case passes, this one is informational; we still assert
    so a future regression in the per-call cost shows up at 10k as
    "would blow budget at scale" instead of waiting for it to break
    at 100k.
    """
    from backend.intent.classifier.llm_based import LLMClassifier

    classifier = LLMClassifier()
    classifier_cost = classifier._build_stats(
        "x" * 1100, "x" * 80, latency_ms=500, cache_hit=False
    ).cost_usd
    advisory_cost = classifier._build_stats(
        "x" * 1500, "x" * 800, latency_ms=2000, cache_hit=False
    ).cost_usd

    daily_cost = (
        10_000 * 0.25 * 0.70 * classifier_cost
        + 10_000 * 0.05 * advisory_cost
    )
    monthly_cost = daily_cost * 30
    print(f"\n[perf] projected monthly cost @ 10000q/day: ${monthly_cost:.2f}")
    assert monthly_cost < 30.0, (
        f"projected ${monthly_cost:.2f}/month exceeds $30 budget"
    )
