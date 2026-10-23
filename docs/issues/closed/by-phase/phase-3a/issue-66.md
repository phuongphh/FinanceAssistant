# Issue #66

[P3A-8] Build Asset Entry Wizard: Real Estate flow

## Epic
Epic 1 — Asset Data Model | **Week 1** | Depends: P3A-3 | Blocks: P3A-9

## Description
Wizard cho BĐS. Phase 3A cover Case A (nhà ở) và Case C (đất). Case B (cho thuê) ở Phase 4.

## Acceptance Criteria
- [ ] Handler `start_real_estate_wizard()` — ask subtype (house_primary, land)
- [ ] Ask name ("Nhà Mỹ Đình", "Đất Ba Vì")
- [ ] Ask address (optional)
- [ ] Ask initial_value + acquired_at (năm mua)
- [ ] Ask current_value (giá ước tính hiện tại)
- [ ] Metadata: `{"address": "...", "area_sqm": null, "year_built": null}`
- [ ] Warning nếu user mention rental: "Cho thuê sắp có ở Phase 4"
- [ ] Support "2 tỷ", "2.5 tỷ", "2500tr"
- [ ] Note: "Bạn sẽ update giá trị BĐS khi có thay đổi"

## Technical Notes
- BĐS không có auto-update
- Phase 3B có thể suggest từ batdongsan.com

## Estimate
~1 day

## Reference
`docs/current/phase-3a-detailed.md` § 1.6 — Real Estate Wizard
