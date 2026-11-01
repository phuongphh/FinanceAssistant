# Issue #341

[Story] P3.9.5-S3: Flow xoá tài sản — chọn type trước

**Parent Epic:** #334 (Epic 1: Tài sản)

## Description
Hiện "Xoá tài sản" liệt kê hết tất cả → quá dài. Pattern mới: chọn asset type trước → list filtered.

## Acceptance Criteria
- [ ] User click "Xoá tài sản" → menu chọn asset type (cổ phiếu/crypto/vàng/BĐS/cash/khác)
- [ ] Sau chọn type → list filtered chỉ assets của type đó
- [ ] Mỗi row có button "🗑 Xoá" với confirmation step
- [ ] Empty type → message "Không có tài sản loại này. [Quay lại]"
- [ ] Shared type filter logic với S14
- [ ] Soft delete via deleted_at (CLAUDE.md rule)

## Estimate: ~0.5 day
## Dependencies: None (S14 sẽ depend shared filter từ Story này)

Close #334
