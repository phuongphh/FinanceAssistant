# Issue #216

[Story] P3.8-S8: Auto-detection job for recurring patterns

**Parent Epic:** #206 (Epic 3: Recurring Transactions + Reminders)

## User Story
As Bé Tiền, tôi muốn tự động phát hiện recurring patterns từ transaction history và gợi ý user confirm — không cần họ phải tự nhớ và add manually.

## Acceptance Criteria
- [ ] `RecurringDetector` class:
  - `detect_patterns(user_id)` → list of suggestions
  - `_group_similar(transactions)` by (category, amount ±10%)
  - `_looks_recurring(group)` heuristic: **3+ occurrences, 25-35 day intervals**
  - `_compute_typical_day(group)` → median day of month
  - `_most_common_merchant(group)` cho context
- [ ] **Cron job** chạy nightly
- [ ] **Telegram delivery — top 3 suggestions/user/run:**
  ```
  🔍 Mình thấy bạn có vẻ trả khoản này hàng tháng:
  
  💸 Thuê nhà • ~15tr • Thường ngày 5 • 4 lần trong 4 tháng
  
  Có phải hàng tháng không?
  [✅ Đúng, ghi nhận] [❌ Không] [✏️ Sửa lại]
  ```
- [ ] **Anti-spam:** rejected pattern → skip future detections
- [ ] **Rate limit:** max 3 suggestions/user/week
- [ ] **Detection logic KHÔNG trigger khi:**
  - Nhiều restaurants khác nhau (different merchants)
  - Amount thay đổi >10% (không consistent)
  - <3 occurrences
- [ ] Test: "thuê nhà 15tr" 4 tháng liên tiếp → detected ✅
- [ ] Test: ăn ở nhiều quán khác nhau 4 lần → NOT detected ✅

## Estimate: ~1.5 day
## Depends on: P3.8-S7
