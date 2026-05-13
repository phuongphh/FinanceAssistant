# Issue #430

[Story] P4B-S13: Life Events Tests + Benchmarks

**Parent Epic:** #415 (Epic 2: Life Event Simulator)

## User Story
Quality gate cho toàn bộ Life Events feature.

## Implementation Tasks
- [ ] tests/twin/test_life_events_engine.py: 5 unit tests
- [ ] tests/life_events/test_service.py: CRUD + soft delete
- [ ] tests/life_events/test_presets.py: preset values
- [ ] tests/integration/test_life_events_flow.py: add → save → recompute triggered
- [ ] benchmarks/bench_life_events.py

## Estimate: ~0.5 day
## Depends on: P4B-S6 to S12

Close #415
