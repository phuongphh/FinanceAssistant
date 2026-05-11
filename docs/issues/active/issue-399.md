# Issue #399

[Story] P4A-S25: Trust framing audit

**Parent Epic:** #374 (Epic 6: Channel-Agnostic Foundation & Polish)

## Description
Every Twin string MUST include uncertainty framing: "có thể", "dự phóng" — NEVER "sẽ", "chắc chắn".

## Acceptance Criteria
- [ ] Grep content/twin_copy.yaml for banned words → 0 hits
- [ ] Chart watermark verified on all cones
- [ ] FAQ entry "Tại sao Bé Tiền không cho con số chính xác?"
- [ ] vi-localization-checker pass
- [ ] Manual read-aloud test

## Estimate: ~0.5 day
## Dependencies: P4A-S12, P4A-S14, P4A-S16, P4A-S23

Close #374
