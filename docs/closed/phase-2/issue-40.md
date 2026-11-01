# Issue #40

[Phase 2 - Week 2] Empathy Engine — Contextual Emotional Responses

## User Story
As a user, I want the bot to notice when something significant happens with my finances — like overspending, a long silence, or an unusually large purchase — and respond with empathy rather than judgment, so I feel supported instead of shamed.

## Background
Phase 2 - Week 2. This is the feature that makes the bot feel "human". Rule: **never judge, never command, always offer choice**. Requires Issue #37 (DB schema).

## Product Vision (strategy.md)
*"User cảm thấy bot 'hiểu mình', không phải bot generic. Retention tăng mạnh."* Empathy is not a nice-to-have — it is the core of Phase 2's value.

## Tone Rules (MUST follow)
- ❌ Never use: "đừng", "không nên", "phải", "sai", "tệ", "lãng phí"
- ✅ Always: acknowledge context, offer choice, use "mình" and "bạn", keep it short
- ✅ Use empathy phrases: "Mình để ý thấy...", "Không phán xét...", "Mình hiểu..."

## Tasks

### Content File (`content/empathy_messages.yaml`)
- [ ] Create YAML with 8 empathy trigger types, each with 2-3 message variations
- [ ] Triggers to implement:
  1. **over_budget_monthly** — vượt ngân sách tháng >10%, cooldown 14 days
  2. **user_silent_7_days** — không tương tác 7-29 ngày, cooldown 14 days
  3. **user_silent_30_days** — không tương tác 30+ ngày, cooldown 60 days
  4. **large_transaction** — giao dịch > 3x median 30 ngày, cooldown 1 day
  5. **weekend_high_spending** — cuối tuần chi >50% tuần, cooldown 30 days
  6. **payday_splurge** — 3 ngày sau lương chi >35%, cooldown 30 days (with save suggestion)
  7. **first_saving_month** — first month thu > chi, cooldown 0 (once)
  8. **consecutive_over_budget** — vượt ngân sách 3 tháng liên tục cùng category, cooldown 60 days

### Empathy Engine (`app/bot/personality/empathy_engine.py`)
- [ ] `check_all_triggers(user)` — check by priority, return first matching trigger not on cooldown
- [ ] Implement 8 trigger check functions (at minimum 4/8 for MVP, stub remaining):
  - `_check_large_transaction` — skip transfers/internal accounts
  - `_check_user_silent_7_days` and `_check_user_silent_30_days`
  - `_check_weekend_high_spending`
  - (stub remaining 4 for later)
- [ ] `_is_on_cooldown(user_id, trigger_name, days)` — query `user_events` table
- [ ] `render_message(trigger, user)` — load YAML, random pick, render placeholders
- [ ] `record_fired(user_id, trigger_name)` — save to `user_events` for cooldown tracking

### Scheduled Job (`app/scheduled/check_empathy_triggers.py`)
- [ ] Run every hour, **skip 22:00 – 07:00** (no nighttime messages)
- [ ] Fetch active users (last 60 days)
- [ ] Per user: check triggers → render message → send → record_fired
- [ ] Daily cap: max **2 empathy messages per user per day**
- [ ] Rate limit: asyncio.sleep(2) between users
- [ ] Error handling: failure per user must not stop loop

## Acceptance Criteria
- [ ] Force-trigger each of the 4+ implemented triggers → correct message sent
- [ ] Cooldown works — same trigger does not fire again within cooldown window
- [ ] Daily cap of 2 empathy messages per user enforced
- [ ] No messages sent between 22:00–07:00
- [ ] Messages read naturally in Vietnamese — no translation artifacts (native speaker review)
- [ ] Skip transfer/internal transactions in large_transaction check

## Reference
`docs/strategy/phase-2-detailed.md` — Sections 2.5 – 2.8
