# Issue #388

[Story] P4A-S14: Twin handler — view trajectory

**Parent Epic:** #371 (Epic 3: Telegram Twin Surface)

## Description
Action (twin, view_current) → snapshot → PNG chart → send photo + Vietnamese caption.

## Acceptance Criteria
- [ ] Caption: cone range "có thể nằm trong khoảng X — Y năm 2036"
- [ ] Cone age noted
- [ ] Empty state cho NW < 10tr
- [ ] Uses Notifier port (NOT direct telegram_service)
- [ ] Test with mocked notifier

## Estimate: ~0.5 day
## Dependencies: P4A-S11, P4A-S13

Close #371
