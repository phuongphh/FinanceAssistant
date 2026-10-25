# Issue #249

[Story] P3.8.5-S6: Profile view + menu integration

**Parent Epic:** #242 (Epic 2: User Profile View)

## User Story
As a user, when I tap `/menu → 👤 Profile của tôi`, I see a comprehensive view of my identity, wealth level, and activity stats — without entering any data.

## Acceptance Criteria

### Profile View Rendering
- [ ] Handler `handle_profile_view` renders full profile
- [ ] Display name: `profile.display_name` OR Telegram first_name OR "Bạn"
- [ ] Format includes:
  - Name + level icon + level name VN (italic description)
  - Account age days
  - Wealth journey: progress bar OR "đã đạt level cao nhất"
  - Net worth change % (if data available)
  - Asset types count
  - Transactions this month
  - Goals active + completed
  - Streak days
  - Briefing read count
- [ ] Markdown formatting
- [ ] 4 edit buttons: 📝 Đổi tên / 🎂 Đổi tuổi / 🔔 Cài thông báo / ◀️ Quay lại

### Menu Integration
- [ ] Add "👤 Profile của tôi" vào Phase 3.6 main menu
- [ ] Callback `menu:profile` → handle_profile_view

### Edge Cases
- [ ] Brand new user (0 assets, 0 transactions) → renders gracefully
- [ ] User without Telegram name → show "Bạn"
- [ ] Net worth = 0 → Khởi Đầu, progress 0%

### Manual Test Scenarios
```
Test 1: Mass Affluent user (Phương, 300tr net worth)
- Open profile: Phương 💎 Trung Lưu Vững
- Shows progress to Tinh Hoa
- Multiple assets, goals, streak

Test 2: Brand new user (Minh)
- Open profile: Minh 🌱 Khởi Đầu
- 0 assets shown gracefully
- Streak: 1
```

## Estimate: ~0.5 day
## Depends on: P3.8.5-S5
