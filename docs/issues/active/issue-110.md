# Issue #110

[Epic] Phase 3.5 — Epic 1: Intent Foundation & Patterns

## Phase 3.5 — Epic 1: Intent Foundation & Patterns

> **Type:** Epic | **Week:** 1 | **Stories:** 6

## Mục tiêu
Build foundational intent classification system dùng **rule-based pattern matching** cho Vietnamese queries. **Không có LLM calls** trong Epic này. Kết thúc Epic 1, Bé Tiền phân loại và trả lời đúng ~75% queries bằng regex patterns.

## Tại Sao Epic Này Quan Trọng
Phase 3A đã có services fetch data (assets, transactions). Cái thiếu là **understanding layer** — khi user gõ free-form text, hệ thống biết họ muốn gì? Epic này build cái cầu nối đó.

## Success Definition
- ✅ Text matching common patterns → correct response
- ✅ 11 real queries từ design phase work end-to-end
- ✅ Zero LLM API calls trong layer này
- ✅ Response time < 200ms cho rule-matched queries
- ✅ Test suite established cho regression prevention

## Stories in this Epic
_(Sẽ update sau khi tạo Story issues)_
- [ ] [Story] P3.5-S1: Define intent types and result data structures
- [ ] [Story] P3.5-S2: Create test fixtures from real queries
- [ ] [Story] P3.5-S3: Build parameter extractors (time, category, ticker, amount)
- [ ] [Story] P3.5-S4: Implement rule-based pattern matching engine
- [ ] [Story] P3.5-S5: Build read query handlers (assets, expenses, market, etc.)
- [ ] [Story] P3.5-S6: Wire intent pipeline into Telegram message router

## Out of Scope
- ❌ LLM fallback — Epic 2
- ❌ Clarification flow — Epic 2
- ❌ Personality wrapping — Epic 3
- ❌ Advisory queries — Epic 3

## Dependencies
- ✅ Phase 3A complete
- ✅ Phase 2 complete (user.display_name, wealth_level)

## Reference
`docs/current/phase-3.5-detailed.md` § Tuần 1
