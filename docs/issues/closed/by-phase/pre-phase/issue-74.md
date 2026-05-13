# Issue #74

[P3A-16] Implement threshold_service.py (income-based expense thresholds)

## Epic
Epic 3 — Storytelling Expense | **Week 3** | Depends: P3A-2 | Blocks: P3A-17

## Description
Tính thresholds (micro + major) adapt theo monthly income. Threshold quyết định giao dịch nào user cần kể chuyện.

## Acceptance Criteria
- [ ] File `app/wealth/services/threshold_service.py`
- [ ] Function `compute_thresholds(monthly_income) -> (micro, major)`
- [ ] Income ranges đúng:
  - <15tr → (100k, 1tr)
  - 15tr – 30tr → (200k, 2tr)
  - 30tr – 60tr → (300k, 3tr)
  - 60tr+ → (500k, 5tr)
- [ ] Function `update_user_thresholds(user_id)` auto-update khi income_streams thay đổi
- [ ] Edge case: income = 0 → default (200k, 2tr)
- [ ] Edge case: income None → default
- [ ] User can manually override via settings
- [ ] Unit tests cover all 4 income brackets + boundary values

## Technical Notes
- Thresholds lưu trong `users` table (added in P3A-1)
- Income = sum(income_streams.amount_monthly) for active streams

## Estimate
~0.5 day

## Reference
`docs/current/phase-3a-detailed.md` § 3.1
