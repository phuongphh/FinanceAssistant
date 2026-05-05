# Issue #180

[Epic] Phase 3.7 — Epic 1: Tool Foundation & DB-Agent (Tier 2)

## Phase 3.7 — Epic 1: Tool Foundation & DB-Agent (Tier 2)

> **Type:** Epic | **Week:** 1 | **Stories:** 5

## Mục tiêu
Build 5 tools + Tier 2 DB-Agent (DeepSeek function calling). **Fix critical bug: "Mã đang lãi?" trả về TẤT CẢ stocks thay vì chỉ winners.**

## Triết Lý Core
- "LLM Selects Tools, Code Executes Tools" — LLM chỉ chọn predefined tool, không generate SQL
- "Extend, Don't Replace" — Phase 3.5 handlers → tools, zero throwaway work
- "Heuristic First" — routing dùng keywords trước, LLM chỉ khi ambiguous

## Success Definition
- ✅ 5 tools implemented + unit tested
- ✅ DB-Agent translates Vietnamese queries → tool calls
- ✅ **Critical test passes:** "Mã đang lãi?" → ONLY gainers
- ✅ Tier 2 latency <3s, cost <$0.0005/query

## Stories in this Epic
- [ ] #183 [Story] P3.7-S1: Define tool schemas with Pydantic
- [ ] #184 [Story] P3.7-S2: Implement GetAssets and GetTransactions tools
- [ ] #185 [Story] P3.7-S3: Implement ComputeMetric, ComparePeriods, GetMarketData tools
- [ ] #186 [Story] P3.7-S4: Build DB-Agent with DeepSeek function calling
- [ ] #187 [Story] P3.7-S5: Implement Tier 2 response formatters

## Dependencies
✅ Phase 3.5 complete | ✅ Phase 3.6 complete

## Parallel: S2 và S3 có thể chạy song song sau S1
