# Issue #419

[Story] P4B-S2: On-Demand Recompute Trigger

**Parent Epic:** #414 (Epic 1: Twin Polish)

## User Story
Khi tôi thêm khoản đầu tư lớn, tôi muốn Bé Tiền tự động cập nhật dự báo — không cần đợi chủ nhật.

## Implementation Tasks
- [ ] Threshold check trong asset_service (change_pct >= 5% net worth)
- [ ] AssetSignificantChangeEvent + publish via event_bus
- [ ] Event consumer với 30-minute debounce per user_id
- [ ] Background recompute task + notification khi xong
- [ ] Layer contract: asset_service chỉ publish event, không recompute trực tiếp

## Acceptance Criteria
- [ ] ≥5% change → recompute trong vòng 30 phút
- [ ] <5% → không trigger
- [ ] 3 changes trong 5 phút → chỉ 1 recompute
- [ ] Notification gửi SAU khi recompute xong

## Estimate: ~1 day
## Depends on: Phase 4A twin recompute task ✅

Close #414
