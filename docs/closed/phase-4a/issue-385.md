# Issue #385

[Story] P4A-S11: Daily snapshot delta read service

**Parent Epic:** #370 (Epic 2: Persistence & Scheduler)

## Description
Read-only — loads latest projection + actual NW → returns delta vs P50.

## Acceptance Criteria
- [ ] get_twin_snapshot(user_id) → TwinSnapshot with latest_cone, actual_nw, delta_vs_p50, cone_age_days, is_stale
- [ ] Stale flag if cone > 14 days old
- [ ] No DB write
- [ ] Used by morning briefing (S15)
- [ ] Unit test fresh/stale/missing cone fixtures

## Estimate: ~0.25 day
## Dependencies: P4A-S8

Close #370
