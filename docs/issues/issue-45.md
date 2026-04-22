# Issue #45

[Phase 2] Exit Criteria Checklist — Gate before Phase 3

## User Story
As a product owner, I want a clear "done" checklist for Phase 2 so that we only proceed to Phase 3 (Zero-Input / SMS capture) when user retention has measurably improved through personality and emotional connection.

## Background
**DO NOT move to Phase 3 until ALL exit criteria below are met.** Phase 3 requires users to trust the bot enough to set up SMS forwarding — that trust is built in Phase 2. A bot without personality at scale will have low retention even with 100% auto-capture.

> From strategy.md: *"Personality trước, feature sau. Phase 2 là đầu tư cho retention — đừng vội bỏ qua vì thấy 'ít code'"*

## Phase 2 Issues Tracker
- [ ] **#37** — DB schema (onboarding, milestones, events, streaks)
- [ ] **#38** — Onboarding 5-step flow
- [ ] **#39** — Milestone detection & celebration
- [ ] **#40** — Empathy engine (8 triggers)
- [ ] **#41** — Streak system
- [ ] **#42** — Weekly fun facts
- [ ] **#43** — Seasonal content calendar
- [ ] **#44** — Weekly goal reminders

## Qualitative Exit Criteria (Beta Feedback)
- [ ] At least **10+ beta users** tested Phase 2 features
- [ ] At least **60% of beta users** describe the bot as: "dễ thương", "ấm áp", "cảm giác như có người thật"
- [ ] Zero users complain about being spammed by the bot
- [ ] Tone is approved by at least 1 native Vietnamese speaker as natural (not translated-from-English)

## Quantitative Exit Criteria (Analytics)
- [ ] Onboarding completion rate **>70%** (track onboarding_completed events)
- [ ] Median onboarding time **<5 minutes**
- [ ] D7 retention of new users **>50%** (improvement from pre-Phase 2 baseline)
- [ ] D30 retention **>30%**
- [ ] At least 3 users have streak **>7 days**

## Anti-patterns Check
- [ ] No empathy messages sent between 22:00–07:00
- [ ] No user receives >2 empathy messages per day
- [ ] No duplicate milestone celebrations
- [ ] All scheduled jobs have error handling (one user failure does not stop the loop)
- [ ] All YAML content files pass yamllint validation (no syntax errors)

## Reference
`docs/strategy/phase-2-detailed.md` — Section "Exit Criteria"
