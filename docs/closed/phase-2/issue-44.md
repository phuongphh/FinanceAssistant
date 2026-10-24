# Issue #44

[Phase 2 - Week 3] Weekly Goal Reminder Based on Onboarding Goal

## User Story
As a user, I want the bot to gently remind me every Monday morning about the financial goal I set during onboarding — and tie it to something concrete from last week's data — so I feel the bot is my personal accountability partner, not just a logging tool.

## Background
Phase 2 - Week 3. Closes the loop from the onboarding goal selection (#38). Users who chose a goal should feel it's remembered and referenced regularly. Requires Issue #37 (schema) and Issue #38 (onboarding) to be done first.

## Design Principle
Reminders must be **data-driven and personal**, not generic motivational quotes. Every reminder should reference actual user data from the past week.

## Tasks

### Memory Moments Module (`app/bot/personality/memory_moments.py`)
- [ ] Define `GOAL_REMINDER_TEMPLATES` dict with 2-3 variations per goal type:
  - **save_more**: reference how much they saved last week vs. target
  - **understand**: surface top category of last week with amount
  - **reach_goal**: show remaining distance to their savings goal
  - **less_stress**: highlight a positive signal (e.g., "under budget in 3 categories")
- [ ] `send_weekly_goal_reminder(user)`:
  - Fetch relevant context from `ReportService` based on user.primary_goal
  - Pick random template variation
  - Render with real data
  - Send message
- [ ] Skip if user has no `primary_goal` set
- [ ] Skip if user was inactive in the past 7 days (no point reminding)

### Context Fetching per Goal
- [ ] **save_more**: weekly saving amount, whether positive or negative
- [ ] **understand**: top spending category name + amount for last 7 days
- [ ] **reach_goal**: fetch nearest active goal, compute remaining amount
- [ ] **less_stress**: count categories that were under budget this week → positive framing

### Scheduled Job (`app/scheduled/weekly_goal_reminder.py`)
- [ ] Run every **Monday at 08:30**
- [ ] Fetch users with onboarding completed + active in last 7 days
- [ ] Call `send_weekly_goal_reminder` per user
- [ ] asyncio.sleep(1) between users

## Acceptance Criteria
- [ ] User with goal=save_more receives message referencing actual last week savings
- [ ] User with no goal → no reminder sent
- [ ] User inactive last week → no reminder sent
- [ ] 4 goal types each produce distinct, contextually correct messages
- [ ] Messages feel encouraging, not pushy (tone review by native speaker)
- [ ] Manually trigger for test user → correct message based on their goal

## Reference
`docs/strategy/phase-2-detailed.md` — Section 3.4
