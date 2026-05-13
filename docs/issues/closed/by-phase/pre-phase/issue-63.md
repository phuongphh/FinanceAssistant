# Issue #63

[P3A-5] Implement Wealth Level detection (Ladder)

## Epic
Epic 1 — Asset Data Model | **Week 1** | Depends: P3A-4 | Blocks: P3A-11

## Description
Detect user's wealth level để adapt UI. 4 levels: Starter, Young Professional, Mass Affluent, HNW.

## Acceptance Criteria
- [ ] File `app/wealth/ladder.py` với `WealthLevel` enum
- [ ] `detect_level(net_worth)` đúng:
  - 0 – 30tr → STARTER
  - 30tr – 200tr → YOUNG_PROFESSIONAL
  - 200tr – 1 tỷ → MASS_AFFLUENT
  - 1 tỷ+ → HIGH_NET_WORTH
- [ ] `next_milestone(net_worth)` returns (target_amount, target_level)
- [ ] Milestone logic cho HNW: tăng dần theo tỷ
- [ ] Unit tests cover boundary values (29tr, 30tr, 200tr, 1 tỷ)
- [ ] Update `user.wealth_level` khi có asset change

## Estimate
~0.5 day

## Reference
`docs/current/phase-3a-detailed.md` § 1.5
