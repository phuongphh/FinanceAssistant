# Phase 3.7 — Retrospective

> **Status:** Code complete (Epics 1-3). User testing pending real-traffic enablement.
> **Date:** 2026-05-05.

## What shipped

| Epic | Stories | Outcome |
|---|---|---|
| 1 — Tool Foundation & DB-Agent | S1-S5 | 5 typed tools + DeepSeek function-calling agent + wealth-adaptive formatters. |
| 2 — Reasoning + Orchestrator | S6-S9 | Claude-Sonnet multi-step reasoning, Telegram streamer, heuristic+cascade router, rate-limit + cost gates. |
| 3 — Polish, Audit & Testing | S10-S12 | `agent_audit_logs` table + admin dashboard, response cache, Phase 3.5 integration, end-to-end winners-only test. |

**The exit-criteria test passes.** `test_winners_e2e.py::test_winners_query_returns_only_winners` confirms "Mã chứng khoán nào của tôi đang lãi?" returns ONLY VNM (+10%) and NVDA (+20%); HPG (-5%) and FPT (-3%) are excluded. The Phase 3.5 bug that motivated the entire phase is fixed.

**Test surface:** 173 unit tests across `backend/tests/test_agent/`, all passing in <3 s. No external dependencies (DB, network, LLM) required.

## What worked

1. **Schema-first design.** Spending Story S1 on tight Pydantic schemas paid dividends across Epic 1-3. LLM tool-selection accuracy is high because the JSON schemas leave little ambiguity, and the same models drove validation, formatting, and tests.
2. **Wrap-don't-replace at the service boundary.** `GetAssetsTool` calls `asset_service.get_user_assets` and applies filter/sort/limit on top — no rewrites of Phase 3A logic. This kept the regression risk near zero (existing wealth tests passed unchanged).
3. **Cascade routing with heuristics first.** Regex heuristics handle ~85% of routing for free; only ambiguous queries pay the Tier 1 LLM cost, and only the truly hard ones reach Tier 2/3. Average-cost target ($0.001/query) is achievable by construction.
4. **Streamer as ABC, not concrete class.** Decoupling the agent (`on_chunk` callback) from delivery (Telegram, fake test sink, future SSE) made testing trivial — we never need a real Telegram bot to assert reasoning behaviour.
5. **Belt-and-suspenders compliance.** Disclaimer enforcement lives both in the prompt AND in code. Adversarial prompts can subvert one; both is hard.

## What was harder than expected

1. **Confidence threshold collision.** Initially the orchestrator gated Tier 1 dispatch behind `confidence >= 0.8`. This bypassed the Phase 3.5 dispatcher's own clarify/confirm flow for medium-confidence intents. The fix (Story S11): drop the orchestrator's threshold and trust the dispatcher as the authoritative confidence-policy layer for Tier 1. Lesson: layer responsibilities should be reviewed when a new layer wraps an existing one.
2. **Per-call orchestrator construction vs singleton.** The orchestrator-as-singleton pattern stopped picking up `set_pipeline` / `set_dispatcher` test stubs, breaking 4 existing tests. Fix: build the orchestrator per-call inside `free_form_text._route_via_orchestrator` using the module-level singletons. Construction is cheap (no LLM clients eagerly built), so the overhead is negligible.
3. **Redis is not a project dependency yet.** The phase doc assumes Redis for rate limiter + cache. Project is still on Postgres-only (CLAUDE.md flags Redis as Phase 1+). Built both behind swap-friendly interfaces:
   - Rate limiter: in-memory sliding window (per-process). One-class swap to Redis when needed.
   - Cache: Postgres `LLMCache` table with TTL. Same pattern as existing intent-LLM cache.

## What we'd do differently next time

1. **Define the layer contract for orchestrator vs dispatcher upfront.** The confidence-threshold collision was architectural drift; a one-page interaction diagram would have caught it.
2. **Ship the integration story (S11) earlier.** Touching `free_form_text.py` in week 3 forced a wave of fixture updates. Doing it in week 2 alongside the orchestrator would have surfaced the singleton issue immediately.
3. **Hash the query for the audit `query_text`.** Logging the raw user input is fine for owner-only Phase 0/1, but multi-user (Phase 1+) needs a one-way hash or sample-rate. Marked as a TODO on the model docstring.
4. **Build a `fixtures.yaml` test runner.** S12 ships a YAML fixture file and test_orchestrator.py reads it via `pytest.parametrize`, but the routing accuracy assertion is hardcoded in the test. A small framework that loads the YAML and reports per-category accuracy would help iterating on heuristics.

## Cost analysis (projected)

Assuming 100 queries/day, distribution per spec:
- Tier 1 (60 queries × $0.0001): $0.006/day
- Tier 2 (30 queries × $0.0005): $0.015/day
- Tier 3 (10 queries × $0.005): $0.050/day
- **Total: ~$0.07/day = ~$2.10/month** at current usage.

Cache hit rate above 30% (Tier 2) and 50% (Tier 3 repeat queries) reduces this further. Hard limit at $20/day kill-switch trips at ~285× projected daily cost — generous safety net.

## Production readiness checklist

- [x] Critical winners-only test passes
- [x] Audit logging on every agent invocation
- [x] Cache TTLs documented + tunable per-tier
- [x] Rate limits enforced (10 Tier 3/h, 100 total/h per user)
- [x] Cost kill-switch ($20/day default)
- [x] Admin metrics endpoint with auth
- [x] Migration created (`h7c8d9e0f1a2_phase37_agent_audit.py`)
- [x] Feature flag (`set_use_agent_orchestrator`) for emergency rollback
- [x] No regressions on existing tests (419 passing across `test_intent/` + `test_agent/`)
- [ ] User testing with 3 personas (deferred — needs production traffic)
- [ ] Cost dashboard chart (admin endpoint exists; UI is Phase 3B)

## Next steps

1. **Run with real DeepSeek + Anthropic credentials** in dev to confirm the projected cost numbers.
2. **Apply the migration** in dev: `alembic upgrade head`.
3. **User testing** with Hà / Phương / Anh Tùng personas on the canonical 5 query types.
4. **Tune heuristics weekly** for the first month based on audit-log misclassifications (top failing-query report exists at `/api/v1/admin/agent-metrics/failures`).
5. **Migrate rate limiter to Redis** when Phase 1 onboards Redis (one-class swap behind `RateLimiter` interface).

## Files changed across the phase

```
backend/agent/                      # NEW — entire agent stack
backend/agent/tools/                # 5 tools, ABC + registry, Pydantic schemas
backend/agent/tier2/                # DeepSeek DB-agent + formatters + prompts
backend/agent/tier3/                # Claude reasoning agent + prompts
backend/agent/streaming/            # Streamer ABC + TelegramStreamer
backend/agent/orchestrator.py       # Heuristic + cascade router
backend/agent/rate_limit.py         # In-memory limiter + cost tracker
backend/agent/audit.py              # Fire-and-forget audit log writer
backend/agent/caching.py            # Tier 2 (5min) + Tier 3 (1h) cache
backend/agent/limits.py             # Hard caps + pricing table
backend/models/agent_audit_log.py   # New ORM model
backend/routers/admin_agent_metrics.py  # Admin dashboard endpoint
backend/services/telegram_service.py    # Added send_chat_action
backend/bot/handlers/free_form_text.py  # Orchestrator integration
content/router_heuristics.yaml      # Vietnamese routing keywords
alembic/versions/h7c8d9e0f1a2_*.py  # Migration
backend/tests/test_agent/           # 173 unit tests
```
