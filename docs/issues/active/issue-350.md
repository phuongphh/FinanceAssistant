# Issue #350

[Story] P3.9.5-S12: Perf Tiền số — target p95 < 2s

**Parent Epic:** #337 (Epic 4: Thị trường)

## Description
Tab Tiền số chậm (>5s). Apply Gold optimization pattern (cache + last_known fallback).

## Acceptance Criteria
- [ ] Identify root cause (provider latency, missing cache, no batching?)
- [ ] Apply fix: Redis cache TTL 120s, last_known fallback, batch fetch nếu >1 coin
- [ ] Benchmark: p95 < 2s (cached), p95 < 4s (cold)
- [ ] Stale-data banner nếu fallback to last_known
- [ ] No new ruff warnings

## Estimate: ~0.75 day
## Dependencies: None (Phase 3.9 cache infrastructure available)

Close #337
