# Issue #206

[Epic] Phase 3.8 — Epic 3: Recurring Transactions + Reminders

## Phase 3.8 — Epic 3: Recurring Transactions + Reminders

> **Type:** Epic | **Week:** 1-2 | **Stories:** 4

## Tại Sao Epic Này Quan Trọng
User explicitly requested reminders ("tôi muốn có reminder cho các khoản chi tiêu hàng tháng"). **Mỗi reminder = 1 daily touchpoint = retention driver.** Đây là engagement strategy, không chỉ utility.

## Success Definition
- ✅ Bot detects monthly recurring patterns từ 6 tháng history
- ✅ Bot gợi ý patterns với confirm/reject buttons
- ✅ User add manual recurring (thuê nhà, internet, gym)
- ✅ Reminders gửi 2 ngày trước expected date
- ✅ Reminder buttons: Đã trả / Trễ vài ngày / Tắt nhắc

## Stories in this Epic
_(Sẽ update sau khi tạo Story issues)_
- [ ] [Story] P3.8-S7: RecurringPattern model + manual entry
- [ ] [Story] P3.8-S8: Auto-detection job for recurring patterns
- [ ] [Story] P3.8-S9: Reminder scheduler + Telegram notifications
- [ ] [Story] P3.8-S10: Reminder action handlers (paid/delay/disable)

## Note
Chạy **song song** với Epic 1 và Epic 2 trong Tuần 1.

## Reference
`docs/current/phase-3.8/phase-3.8-detailed.md` § 1.3
