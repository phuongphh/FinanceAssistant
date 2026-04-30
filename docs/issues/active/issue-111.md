# Issue #111

[Epic] Phase 3.5 — Epic 2: LLM Fallback & Clarification

## Phase 3.5 — Epic 2: LLM Fallback & Clarification

> **Type:** Epic | **Week:** 2 | **Stories:** 5

## Mục tiêu
Augment rule-based foundation với **LLM-powered classification** cho queries không match patterns. Thêm **clarification flows** cho ambiguous queries. Kết thúc Epic 2, Bé Tiền handle 95%+ queries gracefully.

## Tại Sao Epic Này Quan Trọng
Rule-based covers 75% nhưng plateaus ở đó. Real users phrase things unexpected:
- "tôi đang giàu cỡ nào?" (no exact pattern, nhưng rõ ràng hỏi net worth)
- "tháng này tôi xài hoang chưa?" (idiom, hỏi về expenses)

LLM handles those. Nhưng LLM hallucinates → confidence-based dispatching là critical.

## Success Definition
- ✅ Queries không match rules → classified by LLM
- ✅ LLM cost <$0.0005 per query average
- ✅ Medium-confidence (0.5-0.8) → confirmation hoặc safe execution (read intents)
- ✅ Low-confidence (<0.5) → clarifying question
- ✅ Out-of-scope → polite decline

## Stories in this Epic
_(Sẽ update sau khi tạo Story issues)_
- [ ] [Story] P3.5-S7: Implement LLM-based intent classifier
- [ ] [Story] P3.5-S8: Build confidence-based dispatcher with confirm/clarify flows
- [ ] [Story] P3.5-S9: Create clarification message templates (YAML)
- [ ] [Story] P3.5-S10: Implement out-of-scope detection and polite decline
- [ ] [Story] P3.5-S11: Add analytics for classifier accuracy and cost tracking

## Dependencies
- ✅ Epic 1 complete

## Reference
`docs/current/phase-3.5-detailed.md` § Tuần 2
