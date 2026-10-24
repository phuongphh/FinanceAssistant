# Issue #37

[Phase 2 - Week 1] Database Schema — Onboarding, Milestones, Events, Streaks

## User Story
As a developer, I want all Phase 2 database tables and migrations in place so that onboarding state, milestones, empathy events, and streaks can be persisted reliably.

## Background
Phase 2 - Week 1. Foundation task — must complete before any other Phase 2 features.

## Tasks

### Migration 1: Onboarding columns on `users` table
- [ ] `display_name` VARCHAR(50) nullable
- [ ] `primary_goal` VARCHAR(30) nullable (values: save_more, understand, reach_goal, less_stress)
- [ ] `onboarding_step` INTEGER default 0
- [ ] `onboarding_completed_at` DATETIME nullable
- [ ] `onboarding_skipped` BOOLEAN default false
- [ ] Index on `onboarding_step`

### Migration 2: `user_milestones` table
- [ ] id, user_id (FK), milestone_type VARCHAR(50), achieved_at, celebrated_at (nullable), metadata JSON
- [ ] Index on (user_id, milestone_type) and celebrated_at

### Migration 3: `user_events` table (shared log for empathy cooldown + analytics)
- [ ] id, user_id (FK), event_type VARCHAR(50), metadata JSON, timestamp
- [ ] Composite index on (user_id, event_type, timestamp)

### Migration 4: `user_streaks` table
- [ ] user_id (PK, FK), current_streak INTEGER, longest_streak INTEGER, last_active_date DATE

### Model updates
- [ ] Update `app/models/user.py` — add new columns + `is_onboarded` property + `get_greeting_name()`
- [ ] Create `app/models/user_milestone.py` with `MilestoneType` constants class
- [ ] Create `app/models/user_event.py`
- [ ] Create `app/models/streak.py`

## Acceptance Criteria
- [ ] All 4 migrations run cleanly on fresh DB
- [ ] All migrations have working `downgrade()`
- [ ] `user.is_onboarded` returns True when completed or skipped
- [ ] `user.get_greeting_name()` returns display_name or fallback 'bạn'
- [ ] `MilestoneType` constants cover all 15+ milestone types (days_7/30/100/365, savings_1M/5M/10M/50M, streaks, behavior-based)

## Reference
`docs/strategy/phase-2-detailed.md` — Sections 1.1, 2.1, 2.7, 3.1
