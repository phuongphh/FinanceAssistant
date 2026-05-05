# Issue #193

[Story] P3.7-S11: Caching + integration with Phase 3.5

**Parent Epic:** #182 (Epic 3: Polish, Audit & Testing)

## User Story
As a system, tôi cần cache agent responses (Tier 2: 5min, Tier 3: 1h) và integrate Orchestrator vào existing free-form text handler — users transparently benefit from agent without breaking existing flows.

## Acceptance Criteria
- [ ] File `app/agent/caching.py` với `AgentCache` class
- [ ] **Tier 2 cache:**
  - Key: `agent:t2:{user_id}:{tool_name}:{args_hash}`
  - TTL: 5 phút
  - Stores tool result (Pydantic dump)
- [ ] **Tier 3 cache:**
  - Key: `agent:t3:{user_id}:{query_hash}`
  - TTL: 1 giờ
  - Stores response text
- [ ] **Cache invalidation:**
  - Asset add/edit/delete → invalidate user's Tier 2 cache
  - Transaction add → invalidate user's Tier 2 cache
- [ ] **Integration với Phase 3.5:**
  - Update `app/bot/handlers/free_form_text.py`
  - Replace direct intent dispatcher call với `Orchestrator.route(...)`
  - Orchestrator internally falls back to Phase 3.5 dispatcher khi cần
- [ ] **No regressions:**
  - All Phase 3.5 free-form queries vẫn work
  - All Phase 3.5 test fixtures pass
- [ ] **Cache hit rate test:**
  - Same Tier 2 query 5 lần trong 5 phút → 1 LLM call, 4 cache hits
  - Same Tier 3 query trong 1h → cached (no Claude call)

## Implementation Notes
- Redis từ existing setup
- Hash args: `json.dumps(sort_keys=True)` cho consistent keys
- Invalidation: pattern delete `agent:t2:{user_id}:*` khi data thay đổi

## Estimate: ~1 day
## Depends on: Epic 2 complete (parallel với S10)
## Reference: `docs/current/phase-3.7-detailed.md` § 3.2 & 3.3
