# Issue #467

[Story] P4.1-A2: First-Twin shortcut

**Parent Epic:** #463 (Epic A: Pre-Launch Hardening)

## Description
Sau onboarding step 2, auto-trigger Twin computation va push result — KHONG bat user di tim menu.

## Acceptance Criteria
- [ ] OnboardingService.complete_step_2() async-trigger TwinEngineService.compute_for_user()
- [ ] Push result qua Notifier voi intro tu content/onboarding/first_twin_intro.yaml
- [ ] Time-to-first-Twin tu /start <= 5 phut
- [ ] Twin fail -> fallback "dang tinh, quay lai sau 1 phut" + auto-retry 60s
- [ ] Log onboarding completion vao intent_logs

## Estimate: ~1.5 days
## Dependencies: P4.1-A1

Close #463
