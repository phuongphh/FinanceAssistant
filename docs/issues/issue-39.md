# Issue #39

[Phase 2 - Week 2] Milestone Detection & Celebration Messages

## User Story
As a user, I want the bot to remember and celebrate important milestones in my financial journey — like my 7-day streak, 1 month anniversary, or first time saving 10% — so I feel genuinely recognized and motivated to keep going.

## Background
Phase 2 - Week 2. Core retention mechanism — users who receive milestone celebrations have significantly higher D30 retention. Requires Issue #37 (DB schema).

## Product Vision
Strategy: *"80% người bỏ cuộc trong 30 ngày đầu — bạn đã vượt qua. Đây là bước ngoặt đó"*. Milestone messages make users feel seen, not just tracked.

## Tasks

### Content File (`content/milestone_messages.yaml`)
- [ ] Create YAML with Vietnamese messages for all 15+ milestone types
- [ ] Each milestone type has **2-3 message variations** (randomly selected to avoid repetition)
- [ ] Placeholders: {name}, {days}, {count}, {amount}, {goal_progress}
- [ ] Milestone types to cover:
  - Time: days_7, days_30, days_100, days_365
  - Financial: savings_1m, savings_5m, savings_10m, savings_50m, save_10_percent_monthly, save_20_percent_monthly
  - Behavior: first_transaction, first_budget_set, first_voice_input, first_photo_input
  - Streak: streak_7, streak_30, streak_100

### Milestone Service (`app/services/milestone_service.py`)
- [ ] `detect_and_record(user_id)` — run all detection rules, return new milestones
- [ ] `_check_time_milestones(user_id)` — days 7/30/100/365 since account creation
- [ ] `_check_savings_milestones(user_id)` — net savings thresholds
- [ ] `_check_behavior_milestones(user_id)` — first voice, first photo, first budget
- [ ] `get_celebration_message(milestone, user)` — load YAML, pick random variation, render placeholders
- [ ] `mark_celebrated(milestone_id)` — prevent duplicate celebration
- [ ] Deduplication: never create duplicate milestone of same type for same user

### Scheduled Job (`app/scheduled/check_milestones.py`)
- [ ] Run daily at 8:00 AM
- [ ] Fetch all active users (transaction in last 30 days)
- [ ] For each user: detect → record → send celebration → mark celebrated
- [ ] Max 2 milestone messages per user per day (anti-spam)
- [ ] Rate limit: asyncio.sleep(1) between users
- [ ] Error handling: one user failure should not break the loop

### Scheduler Setup
- [ ] Register job in APScheduler (or equivalent) with `cron` trigger at 08:00 daily
- [ ] Add job to app startup lifecycle

## Acceptance Criteria
- [ ] Manually force-trigger each milestone type → celebration message sends correctly
- [ ] Messages render with correct name, amounts, and context
- [ ] Same milestone never celebrates twice for same user
- [ ] No more than 2 milestone messages per user per day
- [ ] YAML file is the single source of truth for message content — no hardcoded strings in Python
- [ ] Messages feel warm and Vietnamese (native speaker review)

## Reference
`docs/strategy/phase-2-detailed.md` — Sections 2.1 – 2.4
