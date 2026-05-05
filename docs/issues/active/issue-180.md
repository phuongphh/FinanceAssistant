# Issue #180

[Epic] Phase 3.7 — Epic 1: Tool Foundation & DB-Agent (Tier 2)

## Phase 3.7 — Epic 1: Tool Foundation & DB-Agent (Tier 2)

> **Type:** Epic | **Week:** 1 | **Stories:** 5

## Context
Phase 3.7 là **architectural inflection point** — biến Bé Tiền từ "intent classifier" thành "AI agent" có thể trả lời 95% queries tài chính cá nhân. Epic 1 build tool system + Tier 2 DB-Agent.

## Mục tiêu
Build 5 tools + Tier 2 DB-Agent (DeepSeek function calling) để handle filter/sort/aggregate/compare queries. **Fix critical bug: "Mã đang lãi?" hiện trả về TẤT CẢ stocks thay vì chỉ winners.**

## Triết Lý Core
- **"LLM Selects Tools, Code Executes Tools"** — LLM không generate SQL, chỉ chọn predefined tool + extract typed params
- **"Extend, Don't Replace"** — Phase 3.5 handlers trở thành tools, zero throwaway work
- **"Heuristic First, LLM When Needed"** — routing dùng keyword heuristics trước, LLM chỉ khi ambiguous

## Success Definition
- ✅ 5 tools implemented + unit tested
- ✅ DB-Agent translates Vietnamese queries → tool calls correctly
- ✅ **Critical test passes:** "Mã chứng khoán nào đang lãi?" returns ONLY gainers
- ✅ Tier 2 average latency <3 seconds
- ✅ Tier 2 cost <$0.0005 per query

## Stories in this Epic
_(Sẽ update sau khi tạo Story issues)_
- [ ] [Story] P3.7-S1: Define tool schemas with Pydantic
- [ ] [Story] P3.7-S2: Implement GetAssets and GetTransactions tools
- [ ] [Story] P3.7-S3: Implement remaining 3 tools (ComputeMetric, ComparePeriods, GetMarketData)
- [ ] [Story] P3.7-S4: Build DB-Agent with DeepSeek function calling
- [ ] [Story] P3.7-S5: Implement Tier 2 response formatters

## Out of Scope
❌ Tier 3 reasoning agent (Epic 2) | ❌ Orchestrator routing (Epic 2) | ❌ Streaming (Epic 2)

## Dependencies
✅ Phase 3.5 complete | ✅ Phase 3.6 complete

## Reference
`docs/current/phase-3.7-detailed.md` § Tuần 1
