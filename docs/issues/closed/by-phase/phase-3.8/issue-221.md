# Issue #221

[Story] P3.8-S13: Goal model + 7 templates YAML

**Parent Epic:** #208 (Epic 5: Goals Management Complete)

## User Story
As a developer building goals, I need Goal model và 7 preset templates trong YAML để goal creation fast và data structured.

## Acceptance Criteria
- [ ] Migration tạo/mở rộng bảng `goals`: id, user_id, name, icon, target_amount, target_date, current_amount, monthly_savings_required, status, priority, linked_assets
- [ ] Model `Goal` với tất cả fields
- [ ] **YAML templates** `content/goal_templates.yaml` — 7 entries:
  - 🚗 Mua xe (200tr-1.5 tỷ, 12-60 months)
  - 🏠 Mua nhà (1.5 tỷ-10 tỷ, 36-120 months)
  - ✈️ Du lịch (10tr-200tr, 3-24 months)
  - 🌅 Hưu trí (3 tỷ-20 tỷ, 120-360 months)
  - 🎓 Học vấn (50tr-1 tỷ, 12-60 months)
  - 💒 Đám cưới (200tr-1 tỷ, 6-24 months)
  - 🛡️ Quỹ khẩn cấp (50tr-500tr, 6-24 months)
- [ ] Mỗi template: id, name, category, icon, typical_amount_range, typical_timeline_months, suggested_questions
- [ ] Service `GoalService.get_templates()` → list of templates

## Estimate: ~0.5 day
## Depends on: None
