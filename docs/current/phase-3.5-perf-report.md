# Phase 3.5 — Performance & Cost Report

> **Story:** [P3.5-S19 / #132](../issues/active/issue-132.md)  
> **Branch:** `claude/implement-epic-1-phase-3.5-dkYqv`  
> **Date measured:** 2026-05-02  
> **Status:** ✅ All targets met — well within budget

This report captures the latency and cost characteristics of the Phase
3.5 intent layer. Numbers are reproducible via
`backend/tests/test_intent/test_performance.py` — re-run after any
change to patterns / prompts / cost model.

---

## Latency

### Rule classifier (in-process regex matching)

| Metric | Target | Measured | Status |
|---|---|---|---|
| p50  | < 50ms  | **0.03ms** | ✅ 1700× under |
| p99  | < 200ms | **0.12ms** | ✅ 1600× under |
| max  | informational | 3.54ms (warm-up) | ✅ |

Sample size: 200 calls across 20 representative queries (10 reps each).

The first call after process start takes ~3ms because regexes compile
lazily on first match. Subsequent calls are sub-millisecond — well
below any user-perceivable latency. Pattern compilation is one-time
overhead at module load (~30 patterns × O(50) chars each).

### Pipeline (rule + LLM fallback, LLM mocked)

| Metric | Target | Measured | Status |
|---|---|---|---|
| p50 | < 1s | **0.03ms** | ✅ |
| p99 | < 3s | **0.08ms** | ✅ |

Mock LLM lets us isolate pipeline orchestration overhead — `await`
plumbing, classifier dispatch, fallback logic. Real-LLM latency is
dominated by network + DeepSeek inference (~500-1500ms p50 in dev
testing); the in-process budget exists to catch regressions in our
own code, not to prove DeepSeek is fast.

### Load test — 100 concurrent queries

| Metric | Target | Measured |
|---|---|---|
| Throughput | ≥ 100 q/min | **24,732 q/sec** |
| Errors | 0 | **0** |
| Total elapsed | < 60s | **0.004s** |

Burst mode (`asyncio.gather` with no rate limiting) — closer to real
Telegram traffic where multiple users tap inline buttons in the same
second than a serial loop would model.

### Voice end-to-end (target informational)

The voice path lives at `backend/bot/handlers/voice_query.py` and
chains:

```
Telegram getFile  →  Whisper transcribe  →  pipeline.classify  →  dispatcher
~150ms              ~1500-2500ms            ~500-1500ms          <100ms
```

Total budget: p50 < 5s, p99 < 8s. Verified manually during user
testing (Story #133); not unit-testable because Whisper cost would
break the CI budget.

---

## Cost

### Per-call cost — LLM classifier

| Component | Value |
|---|---|
| Prompt size (chars / est. tokens) | 1,100 / 275 |
| Response size (chars / est. tokens) | 80 / 14 |
| Cost per call | **$0.000090** |
| Target | < $0.0005 |
| Headroom | 5.5× |

Cost calculation lives in `backend/intent/classifier/llm_based.py`
(`_build_stats`) and follows DeepSeek's published rates as of 2026-04
($0.27/1M input, $1.10/1M output). Update those constants when the
rate card changes; the test will refuse to merge a regression past
$0.0005/call.

### Per-call cost — advisory handler

| Component | Value |
|---|---|
| Prompt size (chars / est. tokens) | 1,500 / 375 |
| Response size (chars / est. tokens) | 800 / 200 |
| Cost per call | **$0.000321** |

Advisory is more expensive than classification because the prompt
includes the user's net worth + breakdown + goals + recent spend, and
the response is up to 200 words of contextual advice. The 5/day
rate limit (issue #127) guarantees a single user can't spike daily
spend even at HNW prompt sizes.

### Cache hit rate

The LLM classifier uses `shared_cache=True` — same query text → one
LLM call across all users (the prompt has no user-identifying
context). Conservative projection assumes 30% cache hit rate, which
matches the empirical figure from `backend/services/llm_service.py`
expense categorization (the closest analog we have).

### Monthly cost projections

| Volume | Mix | Projected cost | Target | Status |
|---|---|---|---|---|
| 1,000 q/day  | 25% LLM, 5% advisory, 30% cache hit | **$0.95/month** | < $5  | ✅ 5× under |
| 10,000 q/day | same mix | **$9.87/month** | < $30 | ✅ 3× under |
| 100,000 q/day | same mix | $98.70/month | < $300 (Phase 3) | ✅ |

Mix assumptions documented in
`backend/tests/test_intent/test_performance.py::test_monthly_cost_projection_under_5_usd_at_1000_per_day`.
Tighten the mix (more rule matches, more cache) and the projection
drops linearly.

### What drives cost — and what protects us

**Drives cost up:**

- New unique queries (cache miss) — every novel phrasing burns ~$0.0001.
- Longer LLM prompts — adding context fields = more tokens.
- Removing the rule layer or making patterns narrower — each rule
  miss escalates to an LLM call.

**Protects cost:**

- Rule layer handles ~75% of queries with ZERO LLM calls. Verified by
  `test_canonical_queries.py::test_classifier_split_across_30_queries`.
- Shared cache de-dupes recurring queries across users.
- Advisory rate limit (5/day) caps the expensive path per user.
- Cost-budget tests in CI block any merge that would push per-call
  cost above the $0.0005 ceiling.

---

## Mitigation plans (if a target slips)

If future telemetry shows real-world numbers diverging from
projections, escalate in this order:

1. **Cache hit rate < 20%** → expand cache TTL from 24h → 7d for the
   classifier (advisory stays uncached because it's user-specific).
2. **Rule rate < 50%** → run Story #134 (pattern improvement) on the
   admin metrics endpoint's "top unclear intents" report.
3. **Advisory cost > $0.50/day** → shorten the prompt's recent-spend
   section or reduce `max_tokens` from 500 → 300.
4. **Pipeline p99 > 3s** → profile via `python -m cProfile` against
   the canonical query suite; suspect culprits are pattern-set growth
   (>200 patterns), per-call YAML re-load, or DB roundtrips in
   `resolve_style`.

---

## Reproducibility

Run the full perf suite locally:

```
python -m pytest backend/tests/test_intent/test_performance.py -v -s
```

The `-s` flag is important — each test prints its measured numbers
via `capsys.disabled()` so a casual run reads like the figures above.
For a quick sanity check on a single PR, the `intent-tests.yml`
GitHub Action runs the assertions (without the `-s` printout) and
blocks merge on any regression.
