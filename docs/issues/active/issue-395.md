# Issue #395

[Story] P4A-S21: Target allocation per wealth level

**Parent Epic:** #373 (Epic 5: Optimal Trajectory & Allocation)

## Description
Table mapping 4 wealth levels → target % per asset class. YAML externalized.

## Acceptance Criteria
- [ ] get_target_allocation(wealth_level) → dict[asset_class, float]
- [ ] 4 levels: Khởi Đầu / Trẻ Năng Động / Trung Lưu Vững / Tinh Hoa
- [ ] Sums = 1.0 ± 0.001
- [ ] Externalizable to content/allocation_targets.yaml
- [ ] Disclaimer "không phải lời khuyên đầu tư" prominent

## Estimate: ~0.5 day
## Dependencies: None

Close #373
