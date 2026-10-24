# Issue #170

[Story] P3.6-S10: Run regression tests on existing flows

**Parent Epic:** #159 (Epic 2: Adaptive Polish & Integration)

## User Story
As a user relies on existing features (asset wizards, OCR, briefing, storytelling), tôi muốn chúng vẫn work sau menu revamp.

## Acceptance Criteria

Run manual regression suite:
- [ ] **Asset wizards:** /add_asset cho cash, stock, real_estate, crypto, gold (5 wizards)
- [ ] **OCR receipt:** Send receipt photo → extracts data
- [ ] **Storytelling:** Tap "💬 Kể chuyện" trong briefing → multi-transaction extract
- [ ] **Morning briefing:** 7 AM trigger fires correctly
- [ ] **Onboarding:** New user /start → completes Phase 2 onboarding
- [ ] **Free-form queries (Phase 3.5):** 11 canonical queries vẫn work
- [ ] **Voice queries:** Voice → transcribe → intent → handle
- [ ] **Mini App dashboard:** Dashboard button → loads correctly

### Cho mỗi flow:
- [ ] Test với 2 personas (Minh Starter + Phương Mass Affluent)
- [ ] Document issues found
- [ ] Fix hoặc escalate trước khi Epic 3 ships

### Definition of Done:
- [ ] All 8+ flows verified working
- [ ] Sign-off doc committed
- [ ] Zero blockers for Epic 3

## Estimate: ~0.5 day (~3h manual testing)
## Depends on: P3.6-S5, P3.6-S6, P3.6-S9
