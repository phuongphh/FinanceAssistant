# Issue #165

[Story] P3.6-S5: Wire menu actions for Tài sản and Chi tiêu

**Parent Epic:** #158 (Epic 1: Menu Structure & Content)

## User Story
As a user tapping "📊 Tổng tài sản" trong Tài sản sub-menu, tôi muốn bot show actual net worth — không phải navigate thêm vào menus.

## Acceptance Criteria

### Tài sản category (5 actions):
- [ ] `menu:assets:net_worth` → reuse Phase 3.5 `QueryAssetsHandler`
- [ ] `menu:assets:report` → 30-day asset report (reuse Phase 3A report logic)
- [ ] `menu:assets:add` → trigger asset wizard từ Phase 3A
- [ ] `menu:assets:edit` → list assets → user chọn → edit wizard
- [ ] `menu:assets:advisor` → reuse Phase 3.5 `AdvisoryHandler` với context "rebalance my portfolio"

### Chi tiêu category (4 actions):
- [ ] `menu:expenses:add` → start text expense entry flow
- [ ] `menu:expenses:ocr` → prompt user: "Gửi ảnh hóa đơn cho mình nhé 📷"
- [ ] `menu:expenses:report` → reuse Phase 3.5 `QueryExpensesHandler`
- [ ] `menu:expenses:by_category` → category breakdown view

### General:
- [ ] **No duplicate logic:** mỗi action reuse existing handler/wizard (DRY)
- [ ] State management đúng khi trigger wizard từ menu
- [ ] **Test:** Tap mỗi trong 9 actions → verify expected flow starts

## Implementation Notes
- "Add asset": cần adapter vì wizard expect Update, callback cho CallbackQuery
- "OCR": chỉ send instruction message, user gửi ảnh bình thường
- "Advisor": synthesize query "tư vấn tối ưu portfolio của tôi" cho AdvisoryHandler

## Estimate: ~1 day
## Depends on: P3.6-S4
## Reference: `docs/current/phase-3.6-detailed.md` § 1.4
