# Issue #383

[Story] P4A-S9: Weekly cron updater (Sunday 23:00)

**Parent Epic:** #370 (Epic 2: Persistence & Scheduler)

## Description
Sunday 23:00 ICT cron iterates active users (logged in 30d), computes both scenarios.

## Acceptance Criteria
- [ ] Existing scheduler infra
- [ ] Concurrency limit 10 parallel
- [ ] Per-user failure isolated, logged
- [ ] Metrics: total, succeeded, failed, total_time
- [ ] Perf: 100 users < 5 minutes
- [ ] Integration test 5 fake users

## Estimate: ~0.5 day
## Dependencies: P4A-S8

Close #370
