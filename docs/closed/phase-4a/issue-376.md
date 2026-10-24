# Issue #376

[Story] P4A-S2: Monte Carlo simulator (single asset)

**Parent Epic:** #369 (Epic 1: Twin Engine)

## Description
Lognormal return path simulation cho 1 asset class.

## Acceptance Criteria
- [ ] `simulate_single_asset(initial, monthly_contrib, dist, years, paths=1000, seed=None) → ndarray[paths, years]`
- [ ] Deterministic với seed
- [ ] Perf: 1000 paths × 10y < 50ms
- [ ] Unit test: P50 of 10y stocks_vn ≈ initial × 1.11^10 ± 10%
- [ ] No NaN/Inf in output

## Estimate: ~0.5 day
## Dependencies: P4A-S1

Close #369
