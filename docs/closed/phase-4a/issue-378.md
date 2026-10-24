# Issue #378

[Story] P4A-S4: Cone aggregator (P10/P50/P90)

**Parent Epic:** #369 (Epic 1: Twin Engine)

## Description
Transform ndarray[paths, years] thành list of (year, p10, p50, p90).

## Acceptance Criteria
- [ ] `aggregate_cone(sim_result, percentiles=[10,50,90]) → list[ConePoint]`
- [ ] Year 0 deterministic (all percentiles = current NW)
- [ ] Decimal, rounded to 1000 VND
- [ ] Monotonic: p10 ≤ p50 ≤ p90 per year

## Estimate: ~0.25 day
## Dependencies: P4A-S3

Close #369
