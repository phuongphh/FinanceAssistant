# Issue #181

[Epic] Phase 3.7 — Epic 2: Premium Reasoning & Orchestrator (Tier 3)

## Phase 3.7 — Epic 2: Premium Reasoning & Orchestrator (Tier 3)

> **Type:** Epic | **Week:** 2 | **Stories:** 4

## Mục tiêu
Build Tier 3 reasoning agent (Claude Sonnet) cho multi-step queries + Orchestrator routing giữa Tier 1/2/3 + streaming UX.

## Tại Sao Epic Này Quan Trọng
Tier 2 handle 25% new queries (filter/sort/aggregate). Tier 3 handle 5% còn lại — advisory, what-if, planning. Cần premium LLM vì real reasoning, không phải tool-calling.

## "Right Model for Right Job"
- **DB queries** → DeepSeek (cheap) → tool calls → DB execution
- **Reasoning queries** → Claude Sonnet (premium) → multi-step thinking

## Success Definition
- ✅ Tier 3 trả lời "Có nên bán FLC?" với multi-step reasoning + disclaimer
- ✅ Orchestrator routes đúng: 85%+ accuracy
- ✅ Streaming: first chunk <2s
- ✅ Cost average <$0.001/query overall
- ✅ Rate limits prevent abuse (10 Tier 3/hour/user)

## Stories in this Epic
_(Sẽ update sau khi tạo Story issues)_
- [ ] [Story] P3.7-S6: Build Reasoning Agent with Claude Sonnet
- [ ] [Story] P3.7-S7: Implement Telegram streaming
- [ ] [Story] P3.7-S8: Build Orchestrator with heuristic routing
- [ ] [Story] P3.7-S9: Add rate limiting and cost caps

## Dependencies
✅ Epic 1 complete

## Reference
`docs/current/phase-3.7-detailed.md` § Tuần 2
