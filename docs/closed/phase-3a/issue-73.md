# Issue #73

[P3A-15] Analytics tracking for morning briefing events

## Epic
Epic 2 — Morning Briefing | **Week 2** | Depends: P3A-12, P3A-14

## Description
Track events để measure retention và engagement của Morning Briefing feature.

## Acceptance Criteria
- [ ] Event `morning_briefing_sent` — properties: user_id, level, timestamp
- [ ] Event `morning_briefing_opened` — user taps any button within 30 min of send
- [ ] Event `briefing_dashboard_clicked`
- [ ] Event `briefing_story_clicked`
- [ ] Event `briefing_add_asset_clicked`
- [ ] Analytics query helpers:
  - Daily open rate (opened / sent)
  - Level breakdown
  - Average time-to-open (seconds)
- [ ] Reuse existing `UserEvent` model (from Phase 2)

## KPIs to measure
- Target: ≥5/7 test users open briefing ≥5/7 days (P3A-25 success criterion)

## Estimate
~0.5 day

## Reference
`docs/current/phase-3a-detailed.md` § metrics section
