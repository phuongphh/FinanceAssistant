# Issue #215

[Story] P3.8-S7: RecurringPattern model + manual entry

**Parent Epic:** #206 (Epic 3: Recurring Transactions + Reminders)

## User Story
As a user, tôi muốn manually add recurring expenses (thuê nhà, internet, gym) và system track chúng để remind tôi trước due date.

## Acceptance Criteria
- [ ] Migration tạo bảng `recurring_patterns`: id, user_id, name, category, expected_amount, schedule, day_of_month, enable_reminders, reminder_days_before, last_occurrence_date, next_expected_date, is_active, source, metadata
- [ ] Migration mở rộng `transactions` table: thêm `is_recurring` (Bool, default False) + `recurrence_id` (FK nullable)
- [ ] Service `RecurringService` với methods:
  - `add_pattern(user_id, name, category, amount, schedule)`
  - `update_pattern(pattern_id, updates)`
  - `disable_pattern(pattern_id)` (soft delete)
  - `get_active_patterns(user_id)`
  - `link_transaction_to_pattern(transaction_id, pattern_id)`
  - `get_next_expected_date(pattern)` — based on last_occurrence + schedule
- [ ] **Manual add via Phase 3.6 menu** dưới Chi tiêu: "🔄 Khoản định kỳ"
  - List existing + "➕ Thêm khoản định kỳ"
  - Wizard: Tên → Số tiền → Loại → Hàng tháng vào ngày? → Bật nhắc nhở?
- [ ] Sample test patterns:
  - "Thuê nhà 15tr ngày 5"
  - "Internet 500k ngày 1"
  - "Netflix 260k ngày 15"

## Estimate: ~1 day
## Depends on: None
