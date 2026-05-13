# Issue #62

[P3A-4] Build NetWorthCalculator

## Epic
Epic 1 — Asset Data Model | **Week 1** | Depends: P3A-3 | Blocks: P3A-11

## Description
Calculate user's net worth từ active assets. Support current + historical + change comparison.

## Acceptance Criteria
- [ ] `NetWorthBreakdown` dataclass: total, by_type dict, asset_count, largest_asset
- [ ] `NetWorthChange` dataclass: current, previous, change_absolute, change_percentage, period_label
- [ ] `calculate(user_id)` returns current breakdown
- [ ] `calculate_historical(user_id, date)` uses latest snapshot ≤ date
- [ ] `calculate_change(user_id, period)` supports "day" | "week" | "month" | "year"
- [ ] Edge case: User with 0 assets → returns total=0, not crash
- [ ] Edge case: No historical snapshots → previous=0
- [ ] Edge case: User just created account → change=0
- [ ] Unit tests cover all 3 methods + edge cases

## Technical Notes
- **QUAN TRỌNG:** Dùng `Decimal`, không `float`
- Historical query: `DISTINCT ON (asset_id)` cho performance
- Cache result trong request

## Estimate
~1 day

## Reference
`docs/current/phase-3a-detailed.md` § 1.4
