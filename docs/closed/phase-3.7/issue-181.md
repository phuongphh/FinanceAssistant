# Issue #181

[Epic] Phase 3.7 — Epic 2: Premium Reasoning & Orchestrator (Tier 3)

## Phase 3.7 — Epic 2: Premium Reasoning & Orchestrator (Tier 3)

> **Type:** Epic | **Week:** 2 | **Stories:** 4

## Mục tiêu
Tier 3 reasoning agent (Claude Sonnet) + Orchestrator routing Tier 1/2/3 + streaming UX cho long responses.

## "Right Model for Right Job"
- DB queries → DeepSeek (cheap) → tool calls
- Reasoning queries → Claude Sonnet (premium) → multi-step thinking

## Success Definition
- ✅ Tier 3 trả lời "Có nên bán FLC?" với multi-step reasoning + disclaimer
- ✅ Orchestrator routing accuracy ≥85%
- ✅ Streaming first chunk <2s
- ✅ Rate limits prevent abuse (10 Tier 3/hour/user)

## Stories in this Epic
- [ ] #188 [Story] P3.7-S6: Build Reasoning Agent with Claude Sonnet
- [ ] #189 [Story] P3.7-S7: Implement Telegram streaming
- [ ] #190 [Story] P3.7-S8: Build Orchestrator with heuristic routing
- [ ] #191 [Story] P3.7-S9: Add rate limiting and cost caps

## Dependencies
✅ Epic 1 complete (#180)
