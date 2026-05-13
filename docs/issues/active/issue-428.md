# Issue #428

[Story] P4B-S11: Mini App Life Events Panel

**Parent Epic:** #415 (Epic 2: Life Event Simulator)

## User Story
Tôi muốn quản lý life events và toggle từng event để xem ảnh hưởng — từ Mini App.

## Implementation Tasks
- [ ] Tab "Kế hoạch" trong Mini App navigation
- [ ] API: GET /api/life-events, GET /api/twin/projection?exclude_event_ids=...
- [ ] Timeline component: events sorted by planned_date
- [ ] Toggle per event → API call → re-render cone chart
- [ ] "Thêm sự kiện" button → deep link to /life_events

## Estimate: ~1 day
## Depends on: P4B-S6, P4B-S8

Close #415
