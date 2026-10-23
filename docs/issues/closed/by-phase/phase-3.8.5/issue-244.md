# Issue #244

[Story] P3.8.5-S1: Feedback model + /feedback command handler

**Parent Epic:** #241 (Epic 1: Feedback System)

## User Story
As a user wanting to share feedback, I want `/feedback` command that lets me send free-form text without choosing categories or filling forms, so I can express thoughts with minimal friction.

## Acceptance Criteria

### Data Model
- [ ] Migration tạo bảng `feedbacks`:
  - content (Text, required)
  - category, sentiment, priority (nullable — populated by classifier)
  - classification_confidence, classifier_version
  - trigger (enum: passive_command | onboarding_day_7 | post_briefing_30d | post_milestone | post_feature_launch)
  - context (JSON snapshot: wealth_level, account_age_days, recent_actions, app_version)
  - status (new | reviewing | actioned | dismissed)
  - admin_notes, created_at, updated_at

### Command Handler
- [ ] `/feedback` command registered
- [ ] Set user state "awaiting_feedback_text"
- [ ] Capture next message as feedback content
- [ ] Capture context snapshot (wealth level, account age, recent 5 actions, phase version)
- [ ] Save to DB immediately (classification deferred async)
- [ ] Confirmation: "✅ Đã ghi nhận! Cảm ơn bạn rất nhiều 💚 Team Bé Tiền sẽ review trong vòng 7 ngày..."
- [ ] Clear state after submission

### Edge Cases
- [ ] Text <5 chars → polite re-prompt
- [ ] Text >5000 chars → reject với explanation
- [ ] Rate limit: max 5 feedbacks/day per user → reject
- [ ] `/cancel` during awaiting state → clear state, acknowledge

### ContextSnapshotService
- [ ] Helper capture user state: wealth_level, account_age_days, recent_actions (last 5), active_features, app_version

## Test Plan
```python
async def test_feedback_creation():
    await send_command(user, "/feedback")
    await send_message(user, "App rất tốt nhưng thiếu dark mode")
    feedback = await Feedback.last_for_user(user.id)
    assert feedback.trigger == "passive_command"
    assert feedback.context["wealth_level"] is not None

async def test_rate_limit():
    for i in range(5): await submit_feedback(user, f"FB {i}")
    response = await submit_feedback(user, "FB 6")
    assert "5/ngày" in response
```

## Estimate: ~1 day
## Depends on: None
## Reference: `phase-3.8.5-detailed.md` § 1.1, 1.2
