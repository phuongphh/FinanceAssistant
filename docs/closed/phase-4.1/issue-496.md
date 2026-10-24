# Issue #496

[Story] P4.1-A1: Onboarding redesign — 3-step goal-based flow

**Parent Epic:** #493 (EPIC 1: Pre-Launch Hardening)

Rewrite /start thanh 3-step guided flow. Step 1 hoi muc tieu (khong phai wealth level).

- [ ] Step 1 — Goal: 3 buttons (Hieu ro tai san / Lap ke hoach / Theo doi chi tieu)
- [ ] Step 2 — First asset: free text VND hoac skip (demo 50tr voi framing ro rang)
- [ ] Step 3 — Auto-trigger Twin (xem A.2)
- [ ] Wealth inference tu asset value: <100tr->starter, 100-500tr->young_pro, 500tr-5ty->mass_affluent, >5ty->hnw
- [ ] Source-aware welcome copy tu users.acquisition_source
- [ ] State machine: goal_question -> first_asset -> twin_shown -> completed
- [ ] Resume mechanism: /start lai mid-flow thi hoi resume hay restart
- [ ] Strings trong content/onboarding/welcome_v2.yaml

Close #493
