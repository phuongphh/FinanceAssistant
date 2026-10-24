# Issue #425

[Story] P4B-S8: Monte Carlo Integration — Life Events

**Parent Epic:** #415 (Epic 2: Life Event Simulator)

## User Story
Khi thêm "Mua nhà 2028", tôi muốn cone chart phản ánh khoản chi đó.

## Implementation Tasks
- [ ] twin/engine/life_events.py: apply_life_events(paths, events, time_grid)
- [ ] Handle one_time_cost: subtract from all paths at event month
- [ ] Handle recurring_monthly_delta: cumulative from event month
- [ ] Floor paths at 0
- [ ] Skip events beyond horizon
- [ ] Integrate vào monte_carlo.py
- [ ] Benchmark: 5 events × 1000 paths × 240 months < 500ms

## Estimate: ~1.5 days
## Depends on: P4B-S6, P4B-S7, Phase 4A MC engine

Close #415
