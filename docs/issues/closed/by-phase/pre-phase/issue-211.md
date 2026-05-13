# Issue #211

[Story] P3.8-S3: Update asset wizard to capture rental data

**Parent Epic:** #204 (Epic 1: Rental Property Tracking)

## User Story
As a user adding BĐS, tôi muốn bot hỏi luôn có phải là BĐS cho thuê không và collect rent/expense info — không cần separate step sau.

## Acceptance Criteria
- [ ] Sau khi nhập basic real_estate info, bot hỏi: "Đây có phải là BĐS cho thuê không?" [✅ Có] [❌ Không]
- [ ] **Nếu ❌ Không** → wizard ends as before
- [ ] **Nếu ✅ Có** → rental sub-wizard:
  - Q1: "Tiền thuê hàng tháng?" (parse VND)
  - Q2: "Chi phí hàng tháng (thuế, sửa chữa)?" (default 0)
  - Q3: "Trạng thái?" [🏠 Đang cho thuê] [🚪 Đang trống]
  - Q4 (if rented): "Thêm thông tin?" [👤 Tên thuê] [📅 Ngày thuê] [✅ Hoàn tất]
- [ ] Confirmation message include computed yield:
  `✅ Đã thêm BĐS cho thuê 'Nhà Mỹ Đình' — Nhận 15tr/tháng (~6.5%/năm)`
- [ ] **Menu action mới** trong Phase 3.6 Tài sản: "🏠 Đánh dấu BĐS cho thuê"
  - List real_estate assets → user chọn → enter rental sub-wizard
- [ ] Validation: rent > 0, expenses ≥ 0, nếu có dates thì end > start
- [ ] Test E2E flow trong real Telegram

## Estimate: ~1 day
## Depends on: P3.8-S2
