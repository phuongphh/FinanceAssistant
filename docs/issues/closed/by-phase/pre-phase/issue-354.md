# Issue #354

[Story] P3.9.5-S16: Rename "Vàng JSC" → "Vàng"

**Parent Epic:** #337 (Epic 4: Thị trường)

## Description
Button "Vàng JSC" có 2 vấn đề: (1) "JSC" không phải brand chuẩn (đúng là "SJC"), (2) label nên ngắn gọn.

## Acceptance Criteria
- [ ] Button "🥇 Vàng JSC" → "🥇 Vàng" trong content/menu_copy.yaml
- [ ] Backend metadata giữ category: "gold", provider: SJC
- [ ] Inside view clarify "Giá theo SJC" trong intro/footer
- [ ] No test snapshot break

## Estimate: ~0.1 day
## Dependencies: None

Close #337
