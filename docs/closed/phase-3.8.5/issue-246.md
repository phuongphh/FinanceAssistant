# Issue #246

[Story] P3.8.5-S3: Active prompts scheduler

**Parent Epic:** #241 (Epic 1: Feedback System)

## User Story
As a product team, I need to proactively prompt users for feedback at key moments — without spamming them. Max 4-6 prompts/year, triggered by real milestones.

## Acceptance Criteria

### YAML Config (`content/feedback_prompts.yaml`)
- [ ] 5 prompts định nghĩa:
  - post_onboarding_day_7 (cooldown 60 days)
  - post_briefing_30_reads (cooldown 90 days)
  - post_first_goal_completed (cooldown 180 days)
  - post_phase_4_launch (cooldown 30 days)
  - post_3_months_active (cooldown 180 days)
- [ ] Mỗi prompt: id, trigger, message, cta_button, skip_button, cooldown_days

### PromptScheduler Service
- [ ] `check_and_send_prompts(user_id)` evaluates triggers
- [ ] Cooldown: skip nếu sent same prompt within cooldown_days
- [ ] **Hard rate limit: max 2 active prompts/user/30 days**
- [ ] Log mỗi prompt sent trong `prompts_sent_log` table

### Event Hooks
- [ ] Briefing read → check post_briefing_30_reads
- [ ] Goal completion → check post_first_goal_completed
- [ ] Daily cron 9 AM → check time-based triggers

### User Interaction
- [ ] Prompt với 2 buttons: CTA ("Chia sẻ cảm nhận") + Skip ("Để sau")
- [ ] CTA → set state awaiting_feedback_text với trigger metadata
- [ ] Skip → log skip, no action

## Test Plan
```python
async def test_cooldown_prevents_resend():
    await send_prompt(user, "post_onboarding_day_7")
    await send_prompt(user, "post_onboarding_day_7")  # 2nd attempt
    sent_count = await PromptsSentLog.count(user.id, "post_onboarding_day_7")
    assert sent_count == 1  # Not 2

async def test_max_2_per_month():
    await send_prompt(user, "post_onboarding_day_7")
    await send_prompt(user, "post_first_goal_completed")
    await send_prompt(user, "post_briefing_30_reads")  # Should be blocked
    assert await PromptsSentLog.count_last_30_days(user.id) == 2
```

## Estimate: ~0.5 day
## Depends on: P3.8.5-S1
