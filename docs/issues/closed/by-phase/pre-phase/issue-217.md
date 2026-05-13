# Issue #217

[Story] P3.8-S9: Reminder scheduler + Telegram notifications

**Parent Epic:** #206 (Epic 3: Recurring Transactions + Reminders)

## User Story
As a user, tôi muốn nhận Telegram reminder 2 ngày trước khi đến hạn khoản định kỳ, với buttons để confirm đã trả hoặc snooze.

## Acceptance Criteria
- [ ] `ReminderScheduler` class:
  - `run_daily()` — chạy 9h sáng via cron
  - Query patterns: enable_reminders=True AND next_expected_date - today ≤ reminder_days_before AND last_reminder_sent != today
- [ ] **Single reminder format:**
  ```
  ⏰ Nhắc nhẹ — [Hôm nay/Ngày mai/X ngày nữa] là tới hạn:
  
  💸 **Thuê nhà** • Dự kiến: 05/06 • ~15,000,000đ
  
  Bạn đã trả chưa?
  [✅ Đã trả] [⏭️ Trễ vài ngày] [🔕 Tắt nhắc]
  ```
- [ ] **Bundled reminder** (3+ patterns cùng ngày):
  ```
  📋 Hôm nay có 3 khoản đến hạn:
  🏠 Thuê nhà — 15,000,000đ
  🌐 Internet — 500,000đ
  🏋️ Gym — 800,000đ
  Tổng: 16,300,000đ
  [✅ Đã trả tất cả] [📝 Ghi chi tiết] [🔕 Tắt nhắc]
  ```
- [ ] Inline keyboard với callbacks: `reminder:paid:{pattern_id}`, `reminder:delay:{pattern_id}`, `reminder:disable:{pattern_id}`
- [ ] Update `last_reminder_sent` sau mỗi send
- [ ] **Don't double-send:** nếu user đã paid (transaction matched pattern this period) → skip
- [ ] Logged trong audit trail

## Estimate: ~1 day
## Depends on: P3.8-S7
