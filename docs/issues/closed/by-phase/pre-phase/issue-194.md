# Issue #194

[Story] P3.7-S12: Comprehensive testing + user trial

**Parent Epic:** #182 (Epic 3: Polish, Audit & Testing)

## User Story
As a product owner shipping Phase 3.7, tôi cần comprehensive test suite covering critical bug, all 5 query types, performance targets, cost projections + 3 real users validating experience.

## ⚠️ CRITICAL TEST (Must Pass)
```python
async def test_winners_query_returns_only_winners():
    # Portfolio: VNM +10%, HPG -5%, NVDA +20%, FPT -3%
    response = await orchestrator.route(
        "Mã chứng khoán nào của tôi đang lãi?", user, mock_handler
    )
    assert "VNM" in response and "NVDA" in response
    assert "HPG" not in response and "FPT" not in response
```

## Acceptance Criteria
- [ ] **Test fixtures** `tests/test_agent/fixtures/tier_test_queries.yaml`:
  - 10 Tier 2 queries (filter, sort, aggregate, compare)
  - 5 Tier 3 queries (advisory, what-if, planning)
  - Expected tier + expected tool/min_tools per query
- [ ] **Test suite** `tests/test_agent/test_orchestrator.py`:
  - Routing accuracy ≥85% on fixtures
  - Cascade fallback works
  - Rate limits enforced
  - Cost caps enforced
- [ ] **Performance verified:**
  - Tier 2 latency p95 <5s
  - Tier 3 first chunk p95 <2s
  - Tier 3 full response p95 <10s
- [ ] **Cost verified:**
  - 100 mixed queries → total ~$0.10 (avg $0.001/query)
- [ ] **Regression suite:**
  - All Phase 3.5 fixture queries pass
  - All Phase 3.6 menu interactions work
  - No degradation in existing features
- [ ] **User testing với 3 users:**
  - 1 Mass Affluent, 1 HNW, 1 Young Professional
  - Mỗi user 30 phút testing
  - Tasks: tất cả 5 query types
  - Document feedback
- [ ] **Retrospective** `docs/current/phase-3.7-retrospective.md`:
  - What worked, what was harder, actual vs projected cost, next steps

## Estimate: ~3 days (1 test + 2 user trial)
## Depends on: P3.7-S10, P3.7-S11
