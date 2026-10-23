# Issue #418

[Story] P4B-S1: Historical Accuracy Tracking

**Parent Epic:** #414 (Epic 1: Twin Polish)

## User Story
Là user đã dùng Twin ≥ 2 tuần, tôi muốn biết dự báo tuần trước chính xác đến đâu so với thực tế.

## Implementation Tasks
- [ ] Alembic migration: ALTER TABLE twin_projections ADD COLUMN actual_net_worth NUMERIC(20,2)
- [ ] Weekly cron: trước khi compute projection mới, điền actual_net_worth cho projection tuần trước
- [ ] Morning briefing accuracy line: "Tuần trước Bé Tiền dự báo P50 = X, thực tế = Y (±Z%)"
- [ ] Tone rules: actual < P10 → reassure; actual > P90 → celebrate; else → neutral
- [ ] Chỉ hiển thị khi có ≥ 2 projections

## Estimate: ~1 day
## Dependencies: Phase 4A ✅

Close #414
