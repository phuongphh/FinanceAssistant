# Issue #169

[Story] P3.6-S9: Verify menu + free-form coexistence

**Parent Epic:** #159 (Epic 2: Adaptive Polish & Integration)

## User Story
As a user biết cả menu và free-form queries (Phase 3.5), tôi muốn dùng either at any time mà không có conflicts.

## Acceptance Criteria

### Scenario 1 — Menu open, then type:
- [ ] Open /menu → main menu visible
- [ ] Send free-form "tài sản của tôi có gì?" (không tap menu)
- [ ] **Expected:** Bot answers trong new message, menu vẫn visible phía trên
- [ ] Old menu message NOT auto-deleted

### Scenario 2 — Type then menu:
- [ ] Send free-form query → bot replies
- [ ] Send /menu → main menu appears below
- [ ] **Expected:** Both messages coexist, no error

### Scenario 3 — Menu while wizard active:
- [ ] Start /add_asset wizard
- [ ] Mid-wizard, send /menu
- [ ] **Expected (pick one):**
  - **(a)** Bot hỏi "Bạn đang trong wizard, hủy trước khi mở menu?" với confirm
  - **(b)** Menu mở bình thường, wizard state preserved
- [ ] **NOT acceptable:** Wizard silently lost OR menu error
- [ ] Document chosen behavior trong code comments

### Scenario 4 — Old callback graceful:
- [ ] Old menu callbacks (`menu_old:*`) → redirect: "Menu đã được nâng cấp! Gõ /menu để xem giao diện mới"
- [ ] Không crash trên unknown callback

## Estimate: ~0.5 day
## Depends on: P3.6-S7
