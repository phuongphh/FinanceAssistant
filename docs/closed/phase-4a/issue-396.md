# Issue #396

[Story] P4A-S22: Optimal trajectory simulator

**Parent Epic:** #373 (Epic 5: Optimal Trajectory & Allocation)

## Description
Reuse Monte Carlo engine với rebalanced allocation + 1.10x savings.

## Acceptance Criteria
- [ ] simulate_optimal(user_portfolio, wealth_level, horizon, savings_boost=1.10) → ndarray
- [ ] Reuses simulate_portfolio (P4A-S3)
- [ ] Same shape as current trajectory
- [ ] Tax/transaction cost ignored (documented)
- [ ] Unit test Mass Affluent fixture

## Estimate: ~0.5 day
## Dependencies: P4A-S3, P4A-S21

Close #373
