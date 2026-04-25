# Issue #67

[P3A-9] Integrate first asset step into onboarding

## Epic
Epic 1 — Asset Data Model | **Week 1** | Depends: P3A-6, P3A-7, P3A-8

## Description
Thêm bước "first asset" sau Phase 2's aha_moment. User thêm ít nhất 1 asset trước khi graduate onboarding.

## Acceptance Criteria
- [ ] Onboarding step `step_6_first_asset` sau `step_5_aha_moment`
- [ ] Keyboard 4 options: Cash (simple), Invest, Real Estate, Skip
- [ ] Tap option → route tới wizard tương ứng
- [ ] "Skip" → lưu `onboarding_skipped_asset=True`, nhắc sau 3 ngày
- [ ] Sau complete first asset → congrats + show first net worth
- [ ] Analytics: `first_asset_added`, `first_asset_skipped`
- [ ] Update `user.onboarding_completed_at` chỉ khi có asset (hoặc skip rõ)

## Technical Notes
- Reuse existing wizards, không duplicate
- State machine: add ONBOARDING_STEP_FIRST_ASSET

## Estimate
~0.5 day

## Reference
`docs/current/phase-3a-detailed.md` § 1.7
