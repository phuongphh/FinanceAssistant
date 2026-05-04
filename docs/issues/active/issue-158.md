# Issue #158

[Epic] Phase 3.6 — Epic 1: Menu Structure & Content

## Phase 3.6 — Epic 1: Menu Structure & Content

> **Type:** Epic | **Week:** 1 | **Stories:** 6

## Mục tiêu
Build 3-level menu hierarchy với 5 main categories (Tài sản, Chi tiêu, Dòng tiền, Mục tiêu, Thị trường), complete content YAML, formatter, và navigation handlers. Kết thúc Epic 1, user có thể /menu và navigate full hierarchy mà không có lỗi.

## Tại Sao Epic Này Quan Trọng
Menu cũ là **expense-tracker era artifact** — flat 8 buttons với "Quét Gmail" deprecated. Menu mới reflects Personal CFO positioning với wealth-first hierarchy.

## Success Definition
- ✅ /menu shows 5-category main menu
- ✅ Tap each category → sub-menu với 4-5 actions
- ✅ Tap action → trigger handler hoặc navigate to wizard
- ✅ "◀️ Quay về" buttons work consistently
- ✅ Edit message in place (no spam new messages)
- ✅ All 5 sub-menus có hint về free-form alternative

## Stories in this Epic
_(Sẽ update sau khi tạo Story issues)_
- [ ] [Story] P3.6-S1: Create menu copy YAML with all 5 categories
- [ ] [Story] P3.6-S2: Build MenuFormatter with basic intros
- [ ] [Story] P3.6-S3: Implement /menu command handler
- [ ] [Story] P3.6-S4: Implement menu callback router
- [ ] [Story] P3.6-S5: Wire menu actions for Tài sản and Chi tiêu
- [ ] [Story] P3.6-S6: Wire menu actions for Dòng tiền, Mục tiêu, Thị trường

## Out of Scope
❌ Wealth-level adaptive intros (Epic 2) | ❌ Migration (Epic 3) | ❌ User testing (Epic 3)

## Dependencies
✅ Phase 3A complete | ✅ Phase 3.5 complete

## Reference
`docs/current/phase-3.6-detailed.md` § Tuần 1
