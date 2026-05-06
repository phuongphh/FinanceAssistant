# Issue #223

[Story] P3.8-S15: Goal wizard + full CRUD via Telegram

**Parent Epic:** #208 (Epic 5: Goals Management Complete)

## User Story
As a user, tôi muốn create/view/update/delete goals từ Telegram menu với 7 templates và projection tự động — không còn stub "Tính năng đang phát triển".

## Acceptance Criteria
- [ ] **Update Phase 3.6 menu** Mục tiêu — tất cả actions functional:
  - `menu:goals:list` — list active goals với progress bars
  - `menu:goals:add` — template picker wizard
  - `menu:goals:update` — update progress
  - `menu:goals:advisor` — projection + feasibility

- [ ] **Add wizard flow:**
  - Q1: 7 template buttons + "✏️ Tự tạo"
  - Q2: "Số tiền mục tiêu?" (parse VND)
  - Q3: "Khi nào muốn đạt?" [6th] [1năm] [2năm] [3năm] [5năm] [Tự nhập] [Bỏ qua]
  - Q4: Show projection summary + feasibility
  - Q5: [✅ Lưu mục tiêu] [📝 Sửa lại]

- [ ] **List view:**
  - Mỗi goal: icon + name + progress bar (▓▓▓░░ 60%)
  - Tap goal → detail: [Update progress] [Edit] [Delete]

- [ ] **Update progress:**
  - "Số tiền mới đã có?"
  - Confirm: "✅ Đã update. Còn Xtr. Dự kiến: [date]"

- [ ] **Delete:** confirm dialog

- [ ] **Empty state:** "Chưa có mục tiêu nào! Mục tiêu đầu tiên của bạn là gì?"

- [ ] Test E2E: create from template → update progress → projection updates

## Estimate: ~1.5 day
## Depends on: P3.8-S14
