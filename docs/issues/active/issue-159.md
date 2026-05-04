# Issue #159

[Epic] Phase 3.6 — Epic 2: Adaptive Polish & Integration

## Phase 3.6 — Epic 2: Adaptive Polish & Integration

> **Type:** Epic | **Week:** 1 (cuối) | **Stories:** 4

## Mục tiêu
Thêm wealth-level adaptive intros để elevate menu từ "functional" sang "personalized". Update Telegram bot menu button. Verify menu tích hợp tốt với existing flows.

## Tại Sao Epic Này Quan Trọng
Epic 1 ships working menu nhưng không "smart". Adaptive intros là thứ làm Bé Tiền có vẻ **biết ai đang dùng nó**. Cùng query "💎 Tài sản" nhưng Minh (Starter) và Anh Tùng (HNW) thấy intro khác nhau.

## Success Definition
- ✅ 4 wealth levels show distinct intros cho mỗi menu screen
- ✅ Bot menu button (Telegram corner) shows updated command list
- ✅ Menu coexists với free-form queries (không conflict)
- ✅ Tất cả Phase 3A wizards vẫn work sau menu integration

## Stories in this Epic
_(Sẽ update sau khi tạo Story issues)_
- [ ] [Story] P3.6-S7: Add wealth-level detection to MenuFormatter
- [ ] [Story] P3.6-S8: Update Telegram bot menu button commands
- [ ] [Story] P3.6-S9: Verify menu + free-form coexistence
- [ ] [Story] P3.6-S10: Run regression tests on existing flows

## Dependencies
✅ Epic 1 complete

## Reference
`docs/current/phase-3.6-detailed.md` § 2.1
