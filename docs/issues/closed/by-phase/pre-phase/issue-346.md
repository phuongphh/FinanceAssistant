# Issue #346

[Story] P3.9.5-S8: Tách riêng card Thu nhập / Chi tiêu

**Parent Epic:** #336 (Epic 3: Dòng tiền)

## Description
Hiện Thu nhập và Chi tiêu hiển thị chung 1 block → khó scan. Tách thành 2 cards độc lập.

## Acceptance Criteria
- [ ] Tổng quan có 2 cards: "💼 Thu nhập tháng" + "💸 Chi tiêu tháng"
- [ ] Mỗi card show: total + top 2-3 sources/categories + delta vs tháng trước
- [ ] Layout consistent với cards khác
- [ ] Money formatting via currency_utils.format_money_short
- [ ] Empty state riêng mỗi card

## Estimate: ~0.5 day
## Dependencies: S7 (clean structure trước khi tách)

Close #336
