# Issue #250

[Story] P3.8.5-S7: Edit display name + age range flows

**Parent Epic:** #243 (Epic 3: User Profile Edit)

## User Story
As a user, I want to change my display name and age range via simple inline flows, so my profile reflects who I am.

## Acceptance Criteria

### Edit Display Name
- [ ] Tap "📝 Đổi tên hiển thị" → bot prompts "Tên mới của bạn?"
- [ ] Set state "awaiting_display_name"
- [ ] Validation: 1-50 chars, sanitize control chars
- [ ] `/cancel` exits gracefully
- [ ] Save → update user_profiles.display_name
- [ ] Confirm với new name, show updated profile

### Edit Age Range
- [ ] Tap "🎂 Đổi nhóm tuổi" → 5 buttons: 20-29, 30-39, 40-49, 50+, 🚫 Không muốn nói
- [ ] Select → update user_profiles.age_range
- [ ] "Không muốn nói" → set NULL
- [ ] Confirm + show updated profile

### Edge Cases
```python
# Empty name → reject
"" → "Tên không được trống."

# Too long → reject
"x" * 51 → "Tên dài quá! Tối đa 50 ký tự nhé."

# SQL injection → sanitize, allow escaped
"'; DROP TABLE users" → save sanitized version

# Emoji OK
"Phương 💚" → accept UTF-8 mb4

# /cancel
"/cancel" → clear state, return to profile view
```

### After Edit
- [ ] Display name change reflects in next briefing/message greeting
- [ ] Profile view shows updated value immediately

## Estimate: ~0.5 day
## Depends on: P3.8.5-S6
