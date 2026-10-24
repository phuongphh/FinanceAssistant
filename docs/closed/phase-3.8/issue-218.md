# Issue #218

[Story] P3.8-S10: Reminder action handlers (paid/delay/disable)

**Parent Epic:** #206 (Epic 3: Recurring Transactions + Reminders)

## User Story
As a user nhận reminder, tôi muốn tap button để ghi nhận đã trả, hoặc snooze 2 ngày, hoặc tắt reminder vĩnh viễn.

## Acceptance Criteria
- [ ] **`reminder:paid:{pattern_id}`:**
  - Wizard: "Số tiền đã trả?" (default = expected_amount)
  - Optional: "Có note gì không?"
  - Create Transaction với is_recurring=True, recurrence_id=pattern_id
  - Update pattern.last_occurrence_date = today
  - Confirm: "✅ Đã ghi nhận. Lần sau dự kiến: [next_expected_date]"
- [ ] **`reminder:delay:{pattern_id}`:**
  - Không tạo transaction
  - Snooze: send lại sau 2 ngày
  - Reply: "⏭️ Hiểu rồi, mình nhắc lại sau 2 ngày."
- [ ] **`reminder:disable:{pattern_id}`:**
  - Set enable_reminders = False
  - Reply: "🔕 OK, không nhắc nữa. Mở lại trong /menu → Chi tiêu → Khoản định kỳ."
- [ ] Test lifecycle đầy đủ: sent → paid → next reminder scheduled

## Estimate: ~0.5 day
## Depends on: P3.8-S9
