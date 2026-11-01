# Issue #348

[Story] P3.9.5-S10: Thêm "Mục tiêu" link tới existing Goals

**Parent Epic:** #336 (Epic 3: Dòng tiền)

## Description
User muốn truy cập Goals từ Cashflow context — tiết kiệm và goals liên quan trực tiếp.

## Acceptance Criteria
- [ ] Button mới "🎯 Mục tiêu" trong submenu Cashflow
- [ ] Click → redirect sang submenu Goals existing (không tạo mới)
- [ ] Action ("cashflow", "goals") → dispatch tới ("goals", "list") handler
- [ ] Test: từ Cashflow click Mục tiêu → goals list render đúng
- [ ] Back button quay lại submenu Cashflow

## Estimate: ~0.25 day
## Dependencies: None

Close #336
