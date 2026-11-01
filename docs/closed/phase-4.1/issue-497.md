# Issue #497

[Story] P4.1-A2: First-Twin shortcut + narrative + in-moment feedback

**Parent Epic:** #493 (EPIC 1: Pre-Launch Hardening)

Sau Step 2, auto-trigger Twin va push 3 messages: mascot narrative, cone chart, feedback prompt.

- [ ] Auto-trigger twin_engine_service.compute() sau Step 2
- [ ] Push 3 messages lien tiep: (1) mascot narrative, (2) cone chart, (3) sau 5-10s feedback prompt voi 3 buttons
- [ ] Feedback buttons: / N / -> luu signal vao onboarding_sessions + feedbacks
- [ ] TTFT < 5 phut tu /start
- [ ] Fallback: "Be Tien dang tinh, quay lai sau 1 phut" (khong  30s)
- [ ] Resume worker: chay moi 5 phut, query session stuck >10 phut, gui 1 message voi 2 button
- [ ] Log onboarding completion vao intent_logs

Close #493
