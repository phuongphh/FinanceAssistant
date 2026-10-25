# Issue #78

[P3A-20] Integrate storytelling with briefing keyboard

## Epic
Epic 3 — Storytelling Expense | **Week 3** | Depends: P3A-14, P3A-18

## Description
Link button "💬 Kể chuyện" từ morning briefing vào storytelling flow. End-to-end integration.

## Acceptance Criteria
- [ ] Button `briefing:story` triggers `start_storytelling()`
- [ ] Context carries source: "from_briefing" vs "direct_command"
- [ ] `/story` command also works
- [ ] End-to-end test: open briefing → tap Kể chuyện → type story → confirm → check DB
- [ ] Analytics: `storytelling_from_briefing` vs `storytelling_direct` (separate events)

## Estimate
~0.5 day
