# Issue #41

[Phase 2 - Week 3] Streak System — Daily Habit Tracking

## User Story
As a user, I want to build and track a daily logging streak so I feel motivated to log at least one transaction every day, turning it into a habit.

## Background
Phase 2 - Week 3. Lightweight gamification — intentionally NOT Duolingo-level. Streaks should feel like a gentle nudge, not pressure. Requires Issue #37 (DB schema).

## Design Principle
*"Không over-gamify — đây là finance app, không phải Duolingo"*. Streaks are a signal for milestone detection, not a leaderboard feature.

## Tasks

### Streak Service (`app/services/streak_service.py`)
- [ ] `record_activity(user_id)` — call every time user logs a transaction
  - First transaction today: increment streak or start new one
  - Already logged today: no-op (idempotent)
  - Gap of 1 day (yesterday was last): continue streak
  - Gap > 1 day: reset to 1
  - Update `longest_streak` if current exceeds it
  - Return dict: {streak_continued: bool, current: int, is_milestone: bool}
- [ ] Milestone thresholds: 7, 30, 100, 365 days trigger `is_milestone: true`

### Integration with Transaction Handler
- [ ] Call `streak_service.record_activity(user.id)` after every successful transaction save
- [ ] If `is_milestone=True` → trigger milestone celebration via `MilestoneService` (streak_7, streak_30, streak_100)

### Streak Display (Optional — show in daily summary)
- [ ] Add streak info to `format_daily_summary` template: "🔥 Streak: {n} ngày"
- [ ] Show in bot /stats command response

## Acceptance Criteria
- [ ] Day 1 transaction → streak = 1
- [ ] Day 2 transaction → streak = 2 (streak_continued = true)
- [ ] Miss a day → next transaction resets streak to 1
- [ ] Log multiple times in same day → streak stays at current value (no double-count)
- [ ] Day 7 → is_milestone = true → milestone celebration fires
- [ ] longest_streak never decreases

## Reference
`docs/strategy/phase-2-detailed.md` — Section 3.1
