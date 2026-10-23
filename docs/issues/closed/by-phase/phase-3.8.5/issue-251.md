# Issue #251

[Story] P3.8.5-S8: Notification settings flow

**Parent Epic:** #243 (Epic 3: User Profile Edit)

## User Story
As a user, I want to toggle briefing/reminders on/off and change their times, so I control when Bé Tiền contacts me.

## Acceptance Criteria

### Notification Menu
- [ ] Tap "🔔 Cài thông báo" → 4 options:
  - Daily Briefing toggle (✅ Bật / 🔕 Tắt)
  - Briefing time (HH:MM)
  - Reminder toggle
  - Reminder time

### Toggle Flows
- [ ] Tap toggle → flip boolean in user_profiles → refresh menu
- [ ] Visual: "✅ Bật" vs "🔕 Tắt"

### Time Change Flows
- [ ] Tap time → preset buttons: 6:00, 7:00, 8:00, 9:00, "✏️ Tự nhập"
- [ ] "Tự nhập" → text input "HH:MM" với validation
- [ ] Save → update respective field

### Cascade Effects (Critical)
- [ ] briefing_enabled=False → morning_briefing_job skips user (check Phase 3.8 job)
- [ ] reminder_enabled=False → ReminderScheduler skips user
- [ ] Time change → next job uses new time

### Edge Cases
```python
# Invalid time
"25:99" → "Giờ không hợp lệ. Format: HH:MM (00:00 - 23:59)"

# Same time for briefing and reminder
# Both should still fire, no collision

# Disable then re-enable
# Don't immediately send — wait for next scheduled time
```

## Estimate: ~0.5 day
## Depends on: P3.8.5-S6
