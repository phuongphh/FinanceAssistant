# Issue #121

[Story] P3.5-S8: Build confidence-based dispatcher with confirm/clarify flows

**Parent Epic:** #111 (Epic 2: LLM Fallback & Clarification)

## User Story
As a user, khi Bé Tiền không chắc tôi muốn gì, tôi muốn nó HỎI thay vì execute sai action — đặc biệt với write operations như ghi tiết kiệm.

## Confidence Routing Matrix

| Confidence | Read Intent | Write Intent |
|-----------|-------------|--------------|
| ≥ 0.8 | Execute | Execute |
| 0.5-0.8 | Execute (safe) | **Confirm trước** |
| < 0.5 | **Clarify** | **Clarify** |

## Acceptance Criteria
- [ ] Update `IntentDispatcher` với full confidence routing
- [ ] **Confirmation flow** cho write intents:
  - Build confirmation message: "Mình hiểu bạn muốn ghi tiết kiệm 1tr. Đúng không?"
  - Inline keyboard: [✅ Đúng] [❌ Không phải]
  - Store pending action trong `context.user_data["pending_action"]`
  - On ✅ → execute, clear pending
  - On ❌ → ask rephrase, clear pending
- [ ] **Clarification flow** cho low-confidence:
  - Load template từ YAML (P3.5-S9)
  - Set state `awaiting_clarification`
  - User's next message → re-route với context
  - Timeout: clarification state expire sau 10 phút
- [ ] **Read fast-path**: medium confidence → execute (read safe, no data damage)
- [ ] Test: "tiết kiệm 1tr" conf 0.85 → execute trực tiếp
- [ ] Test: "tiết kiệm" conf 0.6 → hỏi "tiết kiệm bao nhiêu?"
- [ ] Test: "show stuff" conf 0.3 → unclear với options
- [ ] Test: "tài sản" conf 0.7 → execute (read fast-path)

## Estimate: ~1.5 day
## Depends on: P3.5-S7
## Reference: `docs/current/phase-3.5-detailed.md` § 2.2
