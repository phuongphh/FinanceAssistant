# Issue #173

[Story] P3.6-S13: Cleanup, archive, and documentation updates

**Parent Epic:** #160 (Epic 3: Migration & Quality Assurance)

## User Story
As a future maintainer 6 tháng sau, tôi muốn old menu code archived (không deleted) và documentation updated để reflect current state.

## Acceptance Criteria

### Code cleanup:
- [ ] Move old menu handler → `app/bot/handlers/_archived/menu_v1.py` với header comment
- [ ] Old callback redirect → keep 1 tháng, sau đó tạo issue để remove
- [ ] Tất cả temporary debug logs removed

### Documentation updates:
- [ ] Update `CLAUDE.md`:
  - Remove mention of old menu
  - Add note về 5-category menu mới
  - Update folder structure nếu thay đổi
- [ ] Update `docs/current/strategy.md`:
  - Add note: "Phase 3.6 (Menu UX Revamp) completed [date]"
- [ ] Update `README.md` (screenshots nếu có)
- [ ] Create `docs/current/phase-3.6-retrospective.md`:
  - What worked well
  - What was harder than expected
  - Open questions for Phase 4

### Final checks:
- [ ] Phase 3.6 closed issues → `docs/issues/closed/by-phase/phase-3.6/` (GitHub Action handles)
- [ ] INDEX.md updated
- [ ] 1-week post-deploy: review menu invocation metrics, document baseline vs after

## Estimate: ~0.5 day
## Depends on: P3.6-S11, P3.6-S12
