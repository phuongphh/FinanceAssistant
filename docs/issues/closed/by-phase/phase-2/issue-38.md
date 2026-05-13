# Issue #38

[Phase 2 - Week 1] Onboarding Flow — 5-Step State Machine

## User Story
As a new user, I want a warm, friendly 3-minute onboarding experience that feels personal — asking my name and goal — so I feel like the bot actually knows me from the start.

## Background
Phase 2 - Week 1. This is the **first impression** — quality of writing and flow directly determines retention. Requires Issue #37 (DB schema) to be done first.

## Product Vision (from strategy.md)
Phase 2's goal: user says *"Bot này dễ thương ghê"* or *"Cảm giác như có người thật theo dõi mình"*. Onboarding is where this starts.

## Tasks

### Core State Machine (`app/bot/personality/onboarding_flow.py`)
- [ ] Define `OnboardingStep` enum: NOT_STARTED(0), WELCOME(1), ASKING_NAME(2), ASKING_GOAL(3), FIRST_TRANSACTION(4), COMPLETED(5)
- [ ] Define `PRIMARY_GOALS` dict with 4 options and Vietnamese labels

### 5-Step Handlers (`app/bot/handlers/onboarding.py`)
- [ ] **Step 1 — Welcome**: warm greeting, 2 buttons [✨ Bắt đầu] [⏭ Bỏ qua]
- [ ] **Step 2 — Ask name**: open-ended text prompt, validate length 1-50 chars
- [ ] **Step 3 — Ask goal**: 4 inline buttons, each with personalized follow-up response per goal
- [ ] **Step 4 — First transaction**: invite user to log something, contextualized to their goal
- [ ] **Step 5 — Aha moment**: celebrate first transaction, explain 3 input methods (text/photo/voice)

### Service (`app/services/onboarding_service.py`)
- [ ] `resume_or_start(update, user)` — route to correct step on /start
- [ ] `set_step(user_id, step)`
- [ ] `mark_completed(user_id)` — set completed_at timestamp
- [ ] `mark_skipped(user_id)`
- [ ] `is_in_first_transaction_step(user_id)` — bool check for transaction handler hook

### Integration Points
- [ ] `/start` command → `handle_start_command` (new user = onboard, existing = welcome back)
- [ ] Text message router: if `onboarding_step == ASKING_NAME` → route to name handler
- [ ] Transaction handler: if `is_in_first_transaction_step` → call step 5 after saving
- [ ] Callback handler: route `onboarding:*` callbacks

### Analytics Events
- [ ] Track: `onboarding_started`, `onboarding_step_N_completed`, `onboarding_completed`, `onboarding_skipped`
- [ ] Track duration (created_at → completed_at)

## Acceptance Criteria
- [ ] New user /start → sees warm welcome with 2 buttons (no plain text)
- [ ] Entering name saves to `display_name` and bot uses the name immediately in next message
- [ ] Selecting a goal returns a goal-specific personalized response (4 different responses)
- [ ] After first transaction, step 5 aha message fires automatically
- [ ] /start mid-onboarding → resume from correct step, not restart
- [ ] Skip flow works — user can bypass with ⏭ Bỏ qua
- [ ] End-to-end test: complete full 5-step flow on dev bot in <5 minutes
- [ ] Welcome-back message for already-onboarded users

## Reference
`docs/strategy/phase-2-detailed.md` — Sections 1.2 – 1.4
