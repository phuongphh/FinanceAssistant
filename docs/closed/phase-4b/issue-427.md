# Issue #427

[Story] P4B-S10: Life Event Impact Visualization

**Parent Epic:** #415 (Epic 2: Life Event Simulator)

## User Story
Sau khi thêm "Mua nhà", tôi muốn chart so sánh với/không có sự kiện đó.

## Implementation Tasks
- [ ] twin/charts/impact_chart.py: render_life_event_impact_chart(before_cone, after_cone)
- [ ] 2 cones: Before (xanh) + After (cam)
- [ ] Impact labels tại 2027, 2030, 2035
- [ ] Watermark: "dự phóng, không phải dự đoán"
- [ ] PNG render p95 < 500ms

## Estimate: ~1 day
## Depends on: P4B-S8, P4B-S9

Close #415
