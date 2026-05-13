# Issue #482

[Story] P4.1-A2: First-Twin shortcut

**Parent Epic:** #478 (Epic A: Pre-Launch Hardening)

Sau onboarding step 2, auto-trigger Twin computation — KHONG bat user di tim menu.

- [ ] Async-trigger TwinEngineService.compute_for_user() sau step 2
- [ ] Push result qua Notifier tu content/onboarding/first_twin_intro.yaml
- [ ] Time-to-first-Twin tu /start <= 5 phut
- [ ] Twin fail -> fallback + auto-retry 60s
- [ ] Log onboarding completion vao intent_logs

Close #478
