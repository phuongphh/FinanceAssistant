# Issue #426

[Story] P4B-S9: Telegram Interface — Life Events

**Parent Epic:** #415 (Epic 2: Life Event Simulator)

## User Story
Tôi muốn thêm và quản lý life events ngay trong Telegram.

## Implementation Tasks
- [ ] /life_events command với menu [Xem | Thêm | Xóa]
- [ ] ConversationHandler add flow: SELECT_TYPE → REVIEW_PRESET → CUSTOM_DATE → CUSTOM_COST → CONFIRM
- [ ] Inline keyboards cho event types
- [ ] View list: paginated nếu > 5 events
- [ ] Delete: confirm → soft delete
- [ ] Sau save: trigger S2 recompute + gửi S10 impact chart

## Estimate: ~1.5 days
## Depends on: P4B-S6, P4B-S7, P4B-S8

Close #415
