# Issue #352

[Story] P3.9.5-S14: Button "Sửa tài sản" filtered theo type đang xem

**Parent Epic:** #337 (Epic 4: Thị trường)

## Description
User xem Crypto Portfolios muốn edit 1 coin → hiện phải đi qua menu Tài sản. Add button ngay trong Portfolios view.

## Acceptance Criteria
- [ ] Mỗi Portfolios view (stocks/crypto/gold) có button "✏️ Sửa tài sản"
- [ ] Click → list filtered theo asset_type (reuse S3 logic)
- [ ] Edit giữ context: sau edit → quay về Portfolios view
- [ ] Consistent label cho 3 asset types
- [ ] Empty state: "Chưa có tài sản loại này"

## Estimate: ~0.5 day
## Dependencies: S3 (shared filter helper)

Close #337
