# Issue #190

[Story] P3.7-S8: Build Orchestrator with heuristic routing

**Parent Epic:** #181 (Epic 2: Premium Reasoning & Orchestrator)

## User Story
As Bé Tiền nhận bất kỳ query nào, tôi cần orchestrator quyết định tier nào handle (Phase 3.5 / Tier 2 / Tier 3) dựa trên heuristic keywords với cascade fallback — cheap queries stay cheap, expensive queries justified.

## Acceptance Criteria
- [ ] File `content/router_heuristics.yaml`:
  - `tier2_signals`: filter/sort/aggregate/compare/list keywords (Vietnamese regex)
  - `tier3_signals`: should/plan/what_if/advice/why keywords (Vietnamese)
- [ ] File `app/agent/orchestrator.py` với `Orchestrator` class
- [ ] **`route(query, user, telegram_handler)` method:**
  1. Heuristic classification (`_heuristic_classify`)
  2. Direct route nếu strong signal: tier3 → Tier 3, tier2 → Tier 2
  3. Cascade khi ambiguous: Phase 3.5 first → if conf ≥0.8 use it → else Tier 2 → else Tier 3
- [ ] **Routing accuracy ≥85%** trên 30 test queries
- [ ] Cascade catches misclassified queries
- [ ] Tier 3 ONLY trigger cho clear reasoning signals: "có nên", "làm thế nào để" → NOT "tài sản của tôi"

### Test fixture (30 queries với expected tier):
- [ ] Tier 1: 10 queries (simple direct)
- [ ] Tier 2: 15 queries (filter/sort/aggregate/compare)
- [ ] Tier 3: 5 queries (advisory/planning)

## Test Plan
```python
@pytest.mark.parametrize("query,expected_tier", load_fixtures())
async def test_routing(query, expected_tier):
    orch = Orchestrator()
    actual_tier = orch._heuristic_classify(query)
    assert actual_tier == expected_tier or actual_tier == "ambiguous"
```

## Implementation Notes
- Score-based: count signals per tier, highest wins
- Cache routing decisions per query hash

## Estimate: ~1.5 day
## Depends on: P3.7-S6, P3.7-S7
## Reference: `docs/current/phase-3.7-detailed.md` § 2.2
