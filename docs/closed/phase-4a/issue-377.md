# Issue #377

[Story] P4A-S3: Multi-asset portfolio simulation

**Parent Epic:** #369 (Epic 1: Twin Engine)

## Description
Combine N asset class simulations với correlation matrix.

## Acceptance Criteria
- [ ] `simulate_portfolio(allocation, monthly_savings, savings_split, horizon) → ndarray[paths, years]`
- [ ] Correlation matrix configurable (YAML)
- [ ] Perf: 5 classes × 1000 paths × 10y < 1.5s
- [ ] Unit test: sum of allocation = 1.0 ± 0.001

## Estimate: ~1 day
## Dependencies: P4A-S1, P4A-S2

Close #369
