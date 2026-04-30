# Issue #130: [Story] P3.5-S17: Run regression test suite for existing flows

**GitHub:** https://github.com/phuongphh/FinanceAssistant/issues/130  
**Status:** Open

---

**Parent Epic:** #113 (Epic 4: Quality Assurance)

## User Story
As a user relied on Phase 3A features (asset wizards, briefing, storytelling), tôi muốn chúng vẫn hoạt động đúng — Phase 3.5 phải ADD capabilities, không BREAK existing ones.

## Acceptance Criteria
- [ ] Test asset wizard flows (cash, stock, real_estate) — all work
- [ ] Test storytelling mode (text + voice) — extracts transactions correctly
- [ ] Test morning briefing (7am scheduled) — sends correctly
- [ ] Test daily snapshot job (23:59) — runs correctly
- [ ] Test command handlers (/start, /help, /add_asset) — unchanged
- [ ] Test onboarding flow (Phase 2) — completes correctly
- [ ] Test milestone celebrations (Phase 2) — fire correctly
- [ ] Test empathy triggers (Phase 2) — fire correctly
- [ ] Document any breaking changes (should be zero)
- [ ] Sign-off document committed to `docs/`

## Implementation
- Run via test bot account (không phải production)
- Human walkthrough mỗi flow + record observations
- Check error logs cho unexpected exceptions

## Estimate: ~1 day
## Depends on: Epic 1-3 complete
