# Issue #422

[Story] P4B-S5: Twin Cone Uncertainty Breakdown

**Parent Epic:** #414 (Epic 1: Twin Polish)

## User Story
Tôi muốn biết tại sao cone của tôi rộng — asset nào tạo bất định nhất.

## Implementation Tasks
- [ ] twin/engine/uncertainty.py: compute_uncertainty_breakdown()
- [ ] API: uncertainty_contributors trong projection response
- [ ] Mini App: breakdown table dưới cone chart

## Acceptance Criteria
- [ ] Top 2 asset classes theo contribution % hiển thị
- [ ] Contribution sum ≈ 100%
- [ ] Tooltip: "asset càng volatile → cone càng rộng"

## Estimate: ~0.5 day
## Dependencies: Phase 4A Monte Carlo engine ✅

Close #414
