# Issue #123

[Story] P3.5-S10: Implement out-of-scope detection and polite decline

**Parent Epic:** #111 (Epic 2: LLM Fallback & Clarification)

## User Story
As a user who occasionally types non-finance things ("thời tiết hôm nay", "kể chuyện cười"), tôi muốn Bé Tiền lịch sự nói mình không làm được, thay vì fail silently hoặc show generic menu.

## Acceptance Criteria
- [ ] File `content/out_of_scope_responses.yaml` với response templates
- [ ] Categories handled:
  - Weather: "thời tiết hôm nay"
  - Entertainment: "kể chuyện cười", "hát cho tôi"
  - General knowledge: "thủ đô của Pháp"
  - Personal life: "tôi có nên kết hôn không"
- [ ] Polite decline messages:
  - Acknowledge what user asked
  - Mention what Bé Tiền CAN do
  - Không xin lỗi quá nhiều
  - Warm tone
- [ ] LLM classifier returns `out_of_scope` cho clear OOS queries
- [ ] Dispatcher routes `out_of_scope` → dedicated handler
- [ ] Handler logs OOS query (cho future expansion analysis)
- [ ] OOS detection accuracy >85% trong test fixtures

## Sample
```yaml
out_of_scope_general:
  - |
    Mình chưa biết trả lời câu này {name} ạ 😅
    Mình giúp được về: 💎 Tài sản, 📊 Chi tiêu, 📈 Thị trường, 🎯 Mục tiêu
    Bạn thử hỏi cách khác xem?
```

## Estimate: ~0.5 day
## Depends on: P3.5-S7
