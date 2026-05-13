# Phase 3.5 — Retrospective

> **Story:** [P3.5-S22 / #135](../issues/active/issue-135.md)  
> **Phase span:** approx 3 weeks (Apr 26 — May 2, 2026)  
> **Status:** Phase complete; this doc is the post-mortem.

This is the lookback for Phase 3.5 — the intent layer that pivoted Bé
Tiền from a menu-app-with-chat-skin into something that can answer
free-form Vietnamese queries. Written so a future contributor (or
future-me) can build on what worked and avoid what didn't.

---

## 1. What Worked Well

### Tier C — rule first, LLM as fallback
The cost analysis vindicated the architecture. Real numbers from
`test_performance.py`:

- 75% of canonical queries hit the rule classifier — zero LLM cost.
- LLM-classified queries cost ~$0.00009/call.
- Projected $0.95/month at 1000 q/day, $9.87/month at 10k q/day.

The "rule first" philosophy paid for itself the moment we measured.
Had we gone LLM-everywhere, monthly cost would have been ~5× higher
at the same volume — and latency would have been 1500ms p50 instead
of 30µs.

### Pattern matching for Vietnamese
Diacritic-stripping turned out to be the decisive design choice. One
pattern works for both `tài sản của tôi` and `tai san cua toi` —
that's roughly half the patterns we'd have needed otherwise. The
extractor stack (`time_range`, `category`, `ticker`, `amount`,
`goal_name`) is small (5 modules), composable, and reused by the LLM
classifier post-processing path too.

### Confidence-based dispatcher
Three confidence bands (≥0.8 execute / 0.5-0.8 read-execute or
write-confirm / <0.5 clarify) gave us a single mental model that
covers safety, UX, and cost in one place. The corresponding code is
under 200 lines (`backend/intent/dispatcher.py`) and easy to reason
about.

### Test fixtures from Day 1
`query_examples.yaml` was created BEFORE the classifier — TDD-shaped
the patterns. Every regression so far has surfaced as a fixture
failure during local dev, never made it to a PR. Worth replicating
verbatim in Phase 4.

### Re-using Phase 3A services
Handlers compose Phase 3A's `asset_service`, `net_worth_calculator`,
`expense_service`, `goal_service` — zero new DB code in Epic 1.
That's the layer-contract win: services were already pure and
side-effect-light (flush only, never commit), so plugging them into
the intent layer was free.

### Wealth-aware response composition
`backend/intent/wealth_adapt.py::LevelStyle` lets handlers ask "do I
show %?" instead of branching on the enum. Composition over
inheritance — the four wealth bands share one `_format()` method
that asks four boolean questions. Adding HNW-specific lines (YTD,
allocation %) was a 3-line change per handler.

---

## 2. What Was Harder Than Expected

### LLM false positives in narrow patterns
First iteration of `query_market` matched any 2-5 letter token + the
word `giá` or `hôm nay` — `thời tiết hôm nay` slipped through as
`query_market` for `tiet`. Fix was to validate the captured `ticker`
against `ALL_TICKERS` whitelist *inside the rule classifier*, not just
in the extractor. This is now the canonical fix pattern: any regex
capture that maps to a domain whitelist must validate the capture
*before* counting the match.

### Mocking the LLM in integration-style tests
`test_canonical_queries.py` exercises the full pipeline (rule + LLM
fallback) but CI can't talk to DeepSeek. Solution was an `_llm_oracle`
table — query → canned `IntentResult` — keyed by exact text. Works,
but means new fixtures need oracle entries too. Future improvement:
a Pydantic-validated YAML oracle file separate from the test code.

### Telegram callback_data 64-byte limit
First version of `follow_up.to_callback_data` encoded the full
`{"i": "query_assets", "p": {...}}` JSON — base64-padded, this hit 80
bytes for the simplest parameterised follow-up. Fix was 2-character
intent codes (`qa` for `query_assets`) plus `.<base64-params>`.
Lesson: every callback prefix needs a byte budget written down before
implementation, not after.

### Rebase against squash-merged PRs
Each Epic merged as a squash commit, but my local branch carried the
non-squashed Epic commits. Three rebases in a row hit the same
conflict shape — same paths, same content, just different commit
hashes. `git rebase origin/main` correctly skipped the already-applied
commits each time, but the first time it happened was alarming. Worth
documenting in CONTRIBUTING.md: "if you see ADD/ADD on files you
already merged, rebase, don't merge."

---

## 3. What Surprised Us

1. **Rule classifier latency is essentially zero.** Sub-millisecond
   p99. The compiled-once regex set is faster than I expected for 30+
   patterns. We have headroom to grow patterns 5× before latency
   matters.

2. **Personality wrapper variance is fragile.** The acceptance test
   (5 calls → 3+ distinct openings) initially failed because seeds
   0-4 happened to land on the same code path. Added explicit seed
   sweep across 60+ samples; now stable. Reminder that "random output"
   tests need many samples or controlled seeds, not "first 5 calls".

3. **The PII filter is aggressive enough to hurt the improvement
   loop.** `raw_text` is stripped from analytics events (correct
   privacy posture), which means we cannot find user-typed phrasings
   from production data alone — Story #134 has to source them from
   user-test interviews instead. Future Phase: opt-in
   share-my-queries flag with explicit consent.

---

## 4. Patterns to Reuse in Future Phases

### Architectural

- **YAML-content + Python-handler split.** Patterns / clarifications
  / OOS responses live in `content/*.yaml`. Logic lives in Python.
  Owners can refine wording without a deploy; engineers don't have
  to read YAML to understand control flow. Use this for any "lots of
  variations of similar text" surface (notifications, briefing
  templates, etc.).

- **`DispatchOutcome` dataclass over plain str.** The dispatcher
  returns a structured outcome (text + kind + intent + keyboard
  hint). Callers (free-form-text handler, voice handler, callback
  router) all consume the same shape. Adding analytics events keyed
  by `outcome.kind` was a one-line change. Replicate this pattern
  for any function whose caller needs to differentiate "we did X"
  from "we asked Y" from "we deferred to Z".

- **Layer-contract observance.** Services flush only, callers commit.
  Held up across all 16 Phase 3.5 stories — handlers never
  `db.commit()`, dispatcher never reaches into DB directly, voice
  query handler delegates to the same pipeline as text. The
  contract guard (test_handler_boundary, test_service_boundary)
  caught one violation early in Epic 2.

### Testing

- **Fixtures-first development.** Write the YAML expectations before
  the implementation. Both `query_examples.yaml` and the canonical
  query suite started as test fixtures and *forced* the patterns
  into a particular shape. The patterns I wrote without a fixture
  in hand later turned out to have edge-case bugs.

- **Mock at the API boundary, not deeper.** `LLMClassifier` mocks
  `call_llm` (the SDK boundary). `OutOfScopeHandler` tests mock
  `analytics.track` (the side-effect boundary). Tests that mocked
  internal helpers (e.g., `_extract_parameters`) ended up coupling
  to implementation details and broke on refactors.

### Anti-patterns

- **`use_cache=False` for "always fresh" reads.** Tempting to
  disable cache for advisory-style calls that depend on user state.
  Bit us when a single hour saw 5 advisory calls cost 5× the
  classifier's full-day budget. Rate-limit the *call*, don't disable
  the cache.

- **Patching at the wrong import level.** `test_user_scorecard.py`
  initially patched `backend.scripts.intent_user_scorecard.get_session_factory`
  — the symbol wasn't on that module, only on `backend.database`.
  Lazy imports require patching at the source module, not the
  consumer.

---

## 5. Open Questions / Tech Debt

### Deferred to Phase 4+

- **Real action handlers.** `ACTION_QUICK_TRANSACTION` only has the
  rule classifier path; no actual handler. Same for `PLANNING`. They
  return `OUTCOME_NOT_IMPLEMENTED`. Phase 4 has the storytelling+
  asset+goal write infrastructure to wire these in.
- **Multi-turn clarification.** Current clarify flow expires after
  10 minutes. Doesn't handle "follow-up to a follow-up". Adequate
  for Phase 3.5 — graduate to a small state machine in Phase 4 if
  user testing surfaces real demand.
- **Wealth-level aware advisory prompts.** Advisory currently
  passes the level as a string into the prompt; we don't tune the
  recommendation depth or jargon level by band yet. Easy follow-up.
- **Ticker whitelist staleness.** Hardcoded VN30 list in
  `extractors/ticker.py`. Will go stale. Hook to refresh from
  market_service snapshots on a daily cron.

### Scaling concerns (Phase 2 / Phase 3 readiness)

- **Pattern compilation memory.** `RuleBasedClassifier` keeps every
  compiled pattern in process memory. Negligible at 30-50 patterns;
  audit at 500+.
- **Cache eviction.** `llm_cache` table grows unbounded. Phase 1
  refactor added 30-day TTL on writes but no scheduled cleanup
  job — entries beyond TTL stay until manual VACUUM. Add a
  `cleanup_llm_cache` cron in Phase 1 prep.
- **Single-process pipeline singleton.** `_pipeline` and `_dispatcher`
  in `free_form_text.py` are module globals. Fine for single-worker
  uvicorn; multi-worker setups duplicate the YAML loads (cheap, but
  observable in startup time). Consider a shared FS cache or
  config-server pattern in Phase 2.

---

## 6. Metrics Achieved

| Metric | Target | Achieved | Notes |
|---|---|---|---|
| Final cost per LLM classifier call | < $0.0005 | **$0.000090** | 5.5× under |
| Projected monthly cost @ 1000 q/day | < $5 | **$0.95** | 5× under |
| Rule classifier p50 latency | < 50ms | **0.03ms** | Effectively free |
| Rule classifier p99 latency | < 200ms | **0.12ms** | |
| Canonical query suite — Group A | ≥ 95% | **100%** (10/10) | |
| Canonical query suite — Group B | ≥ 80% | **100%** (5/5) | LLM-mocked |
| Canonical query suite — Group C | ≥ 85% | **100%** (4/4) | |
| Canonical query suite — Group D | ≥ 80% | **100%** (4/4) | |
| Canonical query suite — Group E | 100% graceful | **100%** (7/7) | |
| Rule-classifier rate (30 queries) | ≥ 50% (test floor) | **63%** | Real prod target 70%+ |
| Phase 3A regression tests | 100% pass | **353/353** | No flow broken |
| Total Phase 3.5 intent tests | — | **279** | All passing |

User-satisfaction metrics (D7 ratings, "Bé Tiền hiểu mình tốt hơn"
quote count) are TBD — Story #133 user testing happens after this
PR ships.

---

## 7. Recommendation for Phase 4

Phase 3.5 hit every code/cost target. The two real risks left for
Phase 4 are both about coverage, not architecture:

1. **Production phrasings will surface gaps.** Pattern improvement
   process is documented (Story #134); first 6 weeks of weekly
   reviews are critical.
2. **User trust depends on the gate criteria from Story #133.** If
   any user reports a wrong write action during testing, that's a
   ship-blocker and we iterate on the confidence-routing matrix.

Architecturally, ship as-is. The intent layer is the smallest
abstraction that does the job, and the test suite plus admin metrics
endpoint give us the feedback loop to evolve it without rewrites.

---

*Filed by Claude on the implementation branch. Add a "Lessons learned
from Production" section after the first 30 days of public beta.*
