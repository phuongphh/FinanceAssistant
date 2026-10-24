# Issue #384

[Story] P4A-S10: On-demand recompute trigger

**Parent Epic:** #370 (Epic 2: Persistence & Scheduler)

## Description
Asset CREATE/UPDATE/DELETE hooks → if NW delta > 5% → enqueue background recompute.

## Acceptance Criteria
- [ ] should_recompute(user_id, delta_net_worth) → bool
- [ ] Background via asyncio.create_task
- [ ] Debounce: skip if last compute < 1h ago
- [ ] Test: 3 quick edits → only 1 recompute

## Estimate: ~0.25 day
## Dependencies: P4A-S8

Close #370
