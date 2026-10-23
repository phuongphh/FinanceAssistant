# Issue #466

[Story] P4.1-A1: Onboarding redesign — 3-step guided flow

**Parent Epic:** #463 (Epic A: Pre-Launch Hardening)

## Description
Rewrite /start thanh flow 3 buoc dan dat, dam bao user thay gia tri Be Tien (Twin) ngay session dau.

## Acceptance Criteria
- [ ] /start lan dau hien welcome message < 200 chars + button "Bat dau hanh trinh"
- [ ] 3 buoc voi progress (1/3), (2/3), (3/3):
  - Buoc 1: chon wealth level (4 buttons)
  - Buoc 2: them asset dau tien hoac "De Be Tien dung demo truoc" (placeholder cash 50tr)
  - Buoc 3: trigger first-Twin compute (handoff A2)
- [ ] User cu khong bi qua flow moi
- [ ] Strings trong content/onboarding/welcome_v2.yaml
- [ ] Feature flag ONBOARDING_V2_ENABLED

## Estimate: ~2 days
## Dependencies: None (foundation)

Close #463
