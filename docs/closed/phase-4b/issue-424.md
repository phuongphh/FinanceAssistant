# Issue #424

[Story] P4B-S7: Vietnamese Life Event Presets

**Parent Epic:** #415 (Epic 2: Life Event Simulator)

## User Story
Khi chọn "Mua nhà", tôi muốn Bé Tiền đề xuất con số phù hợp thị trường VN.

## Implementation Tasks
- [ ] life_events/presets.py: dict per LifeEventType → LifeEventPreset
- [ ] Nghiên cứu và cite source (CBRE, VCCI, Bộ GD&ĐT)
- [ ] Content strings → content/vi.yaml key life_event_presets

## Acceptance Criteria
- [ ] 5 types với VN-appropriate defaults
- [ ] Source cited trong comment
- [ ] vi-localization-checker passes

## Estimate: ~0.5 day
## Depends on: P4B-S6

Close #415
