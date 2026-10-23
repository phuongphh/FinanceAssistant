# Issue #345

[Story] P3.9.5-S7: Dedupe — bỏ "So sánh tháng trước" trùng

**Parent Epic:** #336 (Epic 3: Dòng tiền)

## Description
Card "So sánh với tháng trước" overlap với "Thu vs Chi" và "Tỷ lệ tiết kiệm" — cùng số liệu, redundant.

## Acceptance Criteria
- [ ] Identify exact card đang hiển thị duplicate metrics
- [ ] Bỏ phần trùng (giữ "Thu vs Chi" + "Tỷ lệ tiết kiệm" canonical)
- [ ] Hoặc consolidate thành 1 card duy nhất với delta inline
- [ ] User test: report Tổng quan, mỗi metric chỉ xuất hiện 1 lần
- [ ] Không break test snapshots khác

## Estimate: ~0.5 day
## Dependencies: S6 (cùng touch Tổng quan view)

Close #336
