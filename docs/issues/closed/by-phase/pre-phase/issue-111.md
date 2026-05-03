# Issue #111

[Epic] Phase 3.5 — Epic 2: LLM Fallback & Clarification

## Phase 3.5 — Epic 2: LLM Fallback & Clarification

> **Type:** Epic | **Week:** 2 | **Stories:** 5

## Mục tiêu
LLM-powered classification cho queries không match patterns. Clarification flows cho ambiguous queries. Kết thúc Epic 2, Bé Tiền handle 95%+ queries gracefully.

## Success Definition
- ✅ Queries không match rules → LLM classified
- ✅ LLM cost <$0.0005/query average
- ✅ Medium-confidence → confirmation hoặc safe execution
- ✅ Low-confidence → clarifying question
- ✅ Out-of-scope → polite decline

## Stories in this Epic
- [ ] #120 [Story] P3.5-S7: Implement LLM-based intent classifier
- [ ] #121 [Story] P3.5-S8: Build confidence-based dispatcher with confirm/clarify flows
- [ ] #122 [Story] P3.5-S9: Create clarification message templates (YAML)
- [ ] #123 [Story] P3.5-S10: Implement out-of-scope detection and polite decline
- [ ] #124 [Story] P3.5-S11: Add analytics for classifier accuracy and cost tracking

## Dependencies
✅ Epic 1 complete (#110)

## Reference
`docs/current/phase-3.5-detailed.md` § Tuần 2
