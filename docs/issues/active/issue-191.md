# Issue #191

[Story] P3.7-S9: Add rate limiting and cost caps

**Parent Epic:** #181 (Epic 2: Premium Reasoning & Orchestrator)

## User Story
As a product owner, tôi cần hard limits trên per-user query rates và per-query costs để không có single user hoặc buggy code nào spike daily costs unexpectedly.

## Acceptance Criteria
- [ ] File `app/agent/limits.py` với constants:
  - MAX_TOOL_CALLS_PER_QUERY = 5
  - MAX_TOTAL_TOKENS_PER_QUERY = 10000
  - QUERY_TIMEOUT_SECONDS = 30
  - MAX_TIER3_QUERIES_PER_HOUR = 10 (per user)
  - MAX_TOTAL_QUERIES_PER_HOUR = 100 (per user)
- [ ] **Rate limiter** (Redis sliding window):
  - `check_tier3(user_id)` → True if user can make Tier 3 query
  - `check_total(user_id)` → True if under total limit
- [ ] **Enforced trong Orchestrator:**
  - Before Tier 3 call → check rate limit
  - If exceeded → fallback Tier 2 OR show "Bé Tiền đang bận, đợi tý nhé" message
- [ ] **Reasoning agent enforces:**
  - MAX_TOOL_CALLS=5 hard stop
  - asyncio.wait_for(timeout=30) hard stop
- [ ] **Daily cost monitor (Redis):**
  - Track total spend: key `cost:daily:YYYY-MM-DD`
  - Alert nếu >$5/day
  - Hard stop nếu >$20/day (graceful error tới users)
- [ ] **Test rate limits:**
  - 11 Tier 3 queries trong 1h → 11th rejected politely
  - 101 total queries → 101st rejected
- [ ] Failed rate limit KHÔNG silent — tell user politely

## Estimate: ~1 day
## Depends on: P3.7-S8
## Reference: `docs/current/phase-3.7-detailed.md` § 2.4
