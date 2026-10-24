# Issue #382

[Story] P4A-S8: twin_projection_service.compute_and_store

**Parent Epic:** #370 (Epic 2: Persistence & Scheduler)

## Description
Service orchestrate: load portfolio → engine → aggregate cone → INSERT both scenarios.

## Acceptance Criteria
- [ ] Async compute_and_store(user_id, scenario, horizon=10) → TwinProjection
- [ ] Reads via wealth_service + cashflow_service (no raw SQL)
- [ ] Both scenarios (current + optimal) trong 1 call
- [ ] Engine version stamped
- [ ] NO db.commit() — caller commits
- [ ] Unit test với mocked engine + DB

## Estimate: ~1 day
## Dependencies: P4A-S6, P4A-S7, Epic 1

Close #370
