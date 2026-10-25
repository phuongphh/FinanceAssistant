# Issue #161

[Story] P3.6-S1: Create menu copy YAML with all 5 categories

**Parent Epic:** #158 (Epic 1: Menu Structure & Content)

## User Story
As a content owner, I need all menu text stored in editable YAML so copy refinement based on user feedback doesn't require code deploys.

## Acceptance Criteria
- [ ] File `content/menu_copy.yaml` exists
- [ ] **Main menu section** với:
  - Title variations cho 4 wealth levels
  - Intro cho 4 wealth levels (placeholder: `{name}`)
  - 5 buttons: 💎 Tài sản, 💸 Chi tiêu, 💰 Dòng tiền, 🎯 Mục tiêu, 📊 Thị trường
  - Hint section với 3 example free-form queries
- [ ] **5 sub-menus**, mỗi cái có:
  - Title (emoji + uppercase category name)
  - 4-level adaptive intros (starter, young_prof, mass_affluent, hnw)
  - 4-5 action buttons + 1 "◀️ Quay về"
  - Mỗi button có: label, callback (`menu:assets:net_worth`), description
  - Hint với 3 free-form queries specific to category
- [ ] Tất cả callback_data **≤ 64 characters** (Telegram limit)
- [ ] Tất cả button labels **≤ 16 characters** (mobile readability)
- [ ] Tất cả intros **≤ 200 words**
- [ ] YAML loads không syntax error
- [ ] `yamllint content/menu_copy.yaml` passes
- [ ] Test: categories order = Tài sản FIRST (wealth-first positioning)

## Implementation Notes
- Buttons identical across wealth levels (chỉ intros khác)
- Tài sản phải là category đầu tiên — wealth-first positioning

## Estimate: ~1 day
## Depends on: None
## Reference: `docs/current/phase-3.6-detailed.md` § 1.2
