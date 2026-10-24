# Phase 3.8.5 — GitHub Issues (Epics + User Stories)

> **Purpose:** 3 Epics chứa 8 User Stories — feedback + profile pre-launch readiness.  
> **Format:** Epic = component group. Stories within = atomic deliverables.  
> **Reference:** [phase-3.8.5-detailed.md](./phase-3.8.5-detailed.md)

---

## 📊 Overview

| Epic | Day | Stories | Goal |
|------|-----|---------|------|
| Epic 1: Feedback System | 1-2 | 3 stories | `/feedback` working + auto-classification + active prompts |
| Epic 2: User Profile (View) | 3 | 3 stories | Profile view với auto-derived stats |
| Epic 3: User Profile (Edit) | 4 | 2 stories | Edit name, age, notifications |

**Total:** 8 user stories across 3 epics, ~3-4 days of work.

---

## 🏷️ GitHub Labels

**Phase 3.8.5 specific:**
- `phase-3.8.5` (color: light-blue)
- `epic`, `story` (existing)
- `feedback`, `profile` (per-component)
- `pre-launch` (priority indicator)

---

# Epic 1: Feedback System

> **Type:** Epic | **Phase:** 3.8.5 | **Day:** 1-2 | **Stories:** 3

## Overview

Build feedback collection system với philosophy "zero friction" — user chỉ gõ `/feedback`, type message, done. Backend tự động classify (category, sentiment, priority) via DeepSeek. Active prompts strict (4-6/year) để collect feedback at key moments.

## Why This Epic Matters

Soft launch tháng 6/2026 cần feedback loop để iterate based on real user signals. Without this, sẽ launch blind. Feedback feature là **critical pre-launch infrastructure**, không phải nice-to-have.

## Success Definition

When Epic 1 is complete:
- ✅ User có thể gửi feedback bằng `/feedback` command (free-form text)
- ✅ Backend auto-classify feedback (category, sentiment, priority)
- ✅ Active prompts trigger sau key events (post-onboarding, post-30-briefings, etc.)
- ✅ Cooldown + rate limit prevent spam
- ✅ Admin có thể query feedback database

## Stories

- [ ] #XXX [Story] P3.8.5-S1: Feedback model + `/feedback` command handler
- [ ] #XXX [Story] P3.8.5-S2: Backend auto-classification (DeepSeek)
- [ ] #XXX [Story] P3.8.5-S3: Active prompts scheduler

## Reference

📖 [phase-3.8.5-detailed.md § Feedback System](./phase-3.8.5-detailed.md)

### Labels
`phase-3.8.5` `epic` `feedback` `pre-launch` `priority-critical`

---

## [Story] P3.8.5-S1: Feedback model + /feedback command handler

**Type:** Story | **Epic:** Epic 1 | **Estimate:** ~1 day | **Depends on:** None

### Reference
📖 [phase-3.8.5-detailed.md § 1.1, 1.2](./phase-3.8.5-detailed.md)

### User Story

As a user wanting to share feedback, I want a simple `/feedback` command that lets me send free-form text without choosing categories or filling forms, so I can express my thoughts with minimal friction.

### Acceptance Criteria

**Data model:**
- [ ] Migration creates `feedbacks` table with all fields per spec
- [ ] Model `Feedback` includes:
  - `content` (Text, required)
  - `category`, `sentiment`, `priority` (nullable — populated by classifier)
  - `confidence`, `classifier_version` (tracking metadata)
  - `trigger` (enum: passive_command | onboarding_day_7 | post_briefing_30d | post_milestone | post_feature_launch)
  - `context` (JSON snapshot of user state)
  - `status` (new | reviewing | actioned | dismissed)
  - `admin_notes`
  - `created_at`, `updated_at`

**Command handler:**
- [ ] `/feedback` command registered
- [ ] Command sets user state to "awaiting_feedback_text"
- [ ] User next message captured as feedback content
- [ ] Captures context snapshot (user wealth level, account age, recent actions, current phase version)
- [ ] Saves feedback to DB immediately (classification deferred)
- [ ] Returns acknowledgment: "✅ Đã ghi nhận! Cảm ơn bạn rất nhiều 💚 Team Bé Tiền sẽ review trong vòng 7 ngày..."
- [ ] Clears user state after submission

**Edge cases:**
- [ ] Empty/too short text (<5 chars) → polite re-prompt
- [ ] Too long text (>5000 chars) → reject với explanation
- [ ] Rate limit: max 5 feedbacks/day per user → reject với explanation
- [ ] `/cancel` during awaiting state → clear state, message acknowledges

**ContextSnapshotService:**
- [ ] Helper service to capture user state at submission time
- [ ] Returns dict with: wealth_level, account_age_days, recent_actions (last 5), active_features, app_version

### Test Plan

```python
async def test_feedback_creation():
    user = await create_test_user()
    await send_command(user, "/feedback")
    response = await send_message(user, "App rất tốt nhưng thiếu dark mode")
    
    assert "Đã ghi nhận" in response
    feedback = await Feedback.last_for_user(user.id)
    assert feedback.content == "App rất tốt nhưng thiếu dark mode"
    assert feedback.trigger == "passive_command"
    assert feedback.context["wealth_level"] is not None
    
async def test_rate_limit():
    user = await create_test_user()
    for i in range(5):
        await submit_feedback(user, f"Feedback {i}")
    
    # 6th attempt should fail
    response = await submit_feedback(user, "Feedback 6")
    assert "5/ngày" in response
```

### Definition of Done

- Migration ran on dev DB
- `/feedback` command end-to-end working in real Telegram
- Edge cases all tested
- Test coverage ≥85%

### Labels
`phase-3.8.5` `story` `backend` `bot-handler` `feedback` `priority-critical`

---

## [Story] P3.8.5-S2: Backend auto-classification (DeepSeek)

**Type:** Story | **Epic:** Epic 1 | **Estimate:** ~0.5 day | **Depends on:** P3.8.5-S1

### Reference
📖 [phase-3.8.5-detailed.md § 1.3 — Backend Auto-Classification](./phase-3.8.5-detailed.md)

### User Story

As a product team analyzing feedback, I need backend to auto-classify each feedback into category + sentiment + priority so I don't manually categorize hundreds of feedbacks.

### Acceptance Criteria

**FeedbackClassifier service:**
- [ ] File `app/feedback/services/classifier.py`
- [ ] Method `classify(content)` returns dict with category, sentiment, priority, confidence, classifier_version
- [ ] Uses DeepSeek (existing infrastructure)
- [ ] Prompt template hard-coded in service (Vietnamese-aware)
- [ ] Categories: bug | suggestion | praise | question | complaint | other
- [ ] Sentiment: positive | neutral | negative
- [ ] Priority: high | medium | low
- [ ] Returns confidence 0-1
- [ ] Fallback on JSON parse error: classify as "other" with confidence=0

**Background queue worker:**
- [ ] Worker process picks up unclassified feedbacks
- [ ] Calls FeedbackClassifier.classify()
- [ ] Updates feedback record với classification results
- [ ] Logs errors, retries failed jobs (max 3 retries)

**Cost discipline:**
- [ ] Verify DeepSeek call ≤$0.0001 per classification
- [ ] Even at 1000 feedbacks/month, cost <$0.10

**Test set:**
- [ ] Manual test với 20 sample feedbacks (5 bug, 5 suggestion, 5 praise, 5 mixed)
- [ ] Classification accuracy ≥80% on test set

### Test Plan

```python
async def test_classify_bug():
    classifier = FeedbackClassifier()
    result = await classifier.classify("Bot không trả lời khi tôi gửi /menu")
    assert result["category"] == "bug"
    assert result["priority"] in ["high", "medium"]
    assert result["confidence"] > 0.5

async def test_classify_praise():
    result = await classifier.classify("Tôi rất thích Bé Tiền, app tuyệt vời!")
    assert result["category"] == "praise"
    assert result["sentiment"] == "positive"

async def test_classify_fallback_on_llm_error():
    # Mock DeepSeek to return invalid JSON
    with mock_deepseek_returning_invalid_json():
        result = await classifier.classify("test")
        assert result["category"] == "other"
        assert result["confidence"] == 0.0
```

### Definition of Done

- Classifier accuracy ≥80% on 20-sample test set
- Background worker processes queue successfully
- Errors logged, retries working
- Cost verified within budget

### Labels
`phase-3.8.5` `story` `backend` `feedback` `priority-high`

---

## [Story] P3.8.5-S3: Active prompts scheduler

**Type:** Story | **Epic:** Epic 1 | **Estimate:** ~0.5 day | **Depends on:** P3.8.5-S1

### Reference
📖 [phase-3.8.5-detailed.md § 1.4 — Active Prompts Scheduler](./phase-3.8.5-detailed.md)

### User Story

As a product team, I need to proactively prompt users for feedback at key moments (post-onboarding, post-major-events) so I get high-quality contextual feedback without spamming users.

### Acceptance Criteria

**YAML config:**
- [ ] File `content/feedback_prompts.yaml` with 5 prompts:
  - post_onboarding_day_7 (cooldown 60 days)
  - post_briefing_30_reads (cooldown 90 days)
  - post_first_goal_completed (cooldown 180 days)
  - post_phase_4_launch (cooldown 30 days)
  - post_3_months_active (cooldown 180 days)
- [ ] Each prompt has: id, trigger, message, cta_button, skip_button, cooldown_days

**PromptScheduler service:**
- [ ] File `app/feedback/services/prompt_scheduler.py`
- [ ] Method `check_and_send_prompts(user_id)` evaluates triggers
- [ ] Trigger evaluation supports conditions like `account_age_days == 7`, `briefing_read_count == 30`, `goals_completed_count == 1`
- [ ] Cooldown check: don't re-send same prompt within cooldown_days
- [ ] Rate limit: max 2 active prompts per user per 30 days (HARD LIMIT)
- [ ] Logs each prompt sent in `prompts_sent_log` table

**Event hooks:**
- [ ] Hook into briefing read event → check post_briefing_30_reads
- [ ] Hook into goal completion event → check post_first_goal_completed
- [ ] Hook into Twin first view event (Phase 4 future) → check post_phase_4_launch
- [ ] Daily cron job (9 AM) → check time-based triggers (account_age_days)

**User interaction:**
- [ ] Prompt sent với 2 buttons: cta_button (e.g., "Chia sẻ cảm nhận") + skip_button (e.g., "Để sau")
- [ ] CTA button → set state "awaiting_feedback_text" với trigger metadata
- [ ] Skip button → log skip, no action
- [ ] If user replies, feedback stored với trigger=prompt_id (not "passive_command")

### Test Plan

```python
async def test_prompt_after_7_days():
    user = await create_user_aged(7)  # account 7 days old
    await PromptScheduler().check_and_send_prompts(user.id)
    
    sent = await PromptsSentLog.get_for_user(user.id)
    assert any(p.prompt_id == "post_onboarding_day_7" for p in sent)

async def test_cooldown_prevents_resend():
    user = await create_user_aged(7)
    await PromptScheduler().check_and_send_prompts(user.id)  # First send
    
    # Try again 5 days later (within cooldown)
    user.account_age = 12
    await PromptScheduler().check_and_send_prompts(user.id)
    
    sent_count = await PromptsSentLog.count_for_user(user.id, prompt_id="post_onboarding_day_7")
    assert sent_count == 1  # Not 2

async def test_max_2_prompts_per_month():
    # Hit rate limit
    user = await create_user_with_many_triggers()
    await send_prompt(user, "post_onboarding_day_7")
    await send_prompt(user, "post_first_goal_completed")
    
    # Third trigger met but should be blocked
    await send_prompt(user, "post_briefing_30_reads")
    
    sent_this_month = await PromptsSentLog.count_for_user_last_30_days(user.id)
    assert sent_this_month == 2  # Not 3
```

### Definition of Done

- All 5 prompts loaded từ YAML
- Cooldown + rate limit enforced
- At least 1 trigger end-to-end tested in real bot
- No spam during testing với multiple triggers

### Labels
`phase-3.8.5` `story` `backend` `feedback` `priority-high`

---

# Epic 2: User Profile (View)

> **Type:** Epic | **Phase:** 3.8.5 | **Day:** 3 | **Stories:** 3

## Overview

Build profile view với auto-derived stats. View-mode primary — user thấy mọi thông tin hệ thống đã biết về họ (wealth level VN, account age, asset diversity, streaks). No data entry forms.

## Success Definition

- ✅ User open `/menu → 👤 Profile của tôi` → see comprehensive profile view
- ✅ Wealth level hiển thị tiếng Việt (Khởi Đầu / Trẻ Năng Động / Trung Lưu Vững / Tinh Hoa)
- ✅ Progress to next level shown
- ✅ Auto-derived stats from existing data (no new data entry needed)

## Stories

- [ ] #XXX [Story] P3.8.5-S4: UserProfile model + WealthLevelMapper
- [ ] #XXX [Story] P3.8.5-S5: ProfileStatsAggregator
- [ ] #XXX [Story] P3.8.5-S6: Profile view + menu integration

## Reference

📖 [phase-3.8.5-detailed.md § Profile](./phase-3.8.5-detailed.md)

### Labels
`phase-3.8.5` `epic` `profile` `pre-launch` `priority-high`

---

## [Story] P3.8.5-S4: UserProfile model + WealthLevelMapper

**Type:** Story | **Epic:** Epic 2 | **Estimate:** ~0.5 day | **Depends on:** None

### Reference
📖 [phase-3.8.5-detailed.md § 2.1, 2.2](./phase-3.8.5-detailed.md)

### Acceptance Criteria

**Data model:**
- [ ] Migration creates `user_profiles` table
- [ ] Model `UserProfile` với:
  - `user_id` (PK + FK to users)
  - `display_name` (nullable, max 50 chars)
  - `age_range` (nullable, enum: "20-29" | "30-39" | "40-49" | "50+")
  - `briefing_enabled` (bool, default true)
  - `briefing_time` (string HH:MM, default "07:00")
  - `reminder_enabled` (bool, default true)
  - `reminder_time` (string HH:MM, default "09:00")
  - `created_at`, `updated_at`

**Wealth Levels YAML:**
- [ ] File `content/wealth_levels.yaml` với 4 levels
- [ ] Each level has: id, name_vn, name_en, icon, net_worth_min, net_worth_max, description
- [ ] **Vietnamese names (locked, do not change):**
  - Khởi Đầu (0-30tr) 🌱
  - Trẻ Năng Động (30-200tr) 🚀
  - Trung Lưu Vững (200tr-1 tỷ) 💎
  - Tinh Hoa (1 tỷ+) 🏆

**WealthLevelMapper service:**
- [ ] `get_level(net_worth)` returns level dict
- [ ] `get_next_level(net_worth)` returns next tier user is working toward
- [ ] `get_progress_to_next(net_worth)` returns progress dict (at_top, progress_pct, amount_to_next, next_level_name)
- [ ] Boundary handling: `>= min AND < max` (consistent across all level checks)

### Test Plan

```python
def test_wealth_level_starter():
    mapper = WealthLevelMapper()
    level = mapper.get_level(Decimal("15000000"))  # 15tr
    assert level["name_vn"] == "Khởi Đầu"
    assert level["icon"] == "🌱"

def test_wealth_level_boundary():
    # 30tr exactly should be Trẻ Năng Động (next tier)
    level = WealthLevelMapper().get_level(Decimal("30000000"))
    assert level["name_vn"] == "Trẻ Năng Động"

def test_progress_to_next():
    # 15tr in Khởi Đầu (0-30tr) — halfway to next
    progress = WealthLevelMapper().get_progress_to_next(Decimal("15000000"))
    assert progress["at_top"] == False
    assert 49 <= progress["progress_pct"] <= 51  # ~50%
    assert progress["next_level_name"] == "Trẻ Năng Động"

def test_progress_at_top():
    # 5 tỷ — already at top tier
    progress = WealthLevelMapper().get_progress_to_next(Decimal("5000000000"))
    assert progress["at_top"] == True
```

### Definition of Done

- 4 levels correctly mapped
- Boundary edge cases tested
- Progress calculation verified với multiple inputs

### Labels
`phase-3.8.5` `story` `backend` `profile` `data-model` `priority-critical`

---

## [Story] P3.8.5-S5: ProfileStatsAggregator

**Type:** Story | **Epic:** Epic 2 | **Estimate:** ~1 day | **Depends on:** P3.8.5-S4

### Reference
📖 [phase-3.8.5-detailed.md § 2.3](./phase-3.8.5-detailed.md)

### User Story

As a profile view, I need an aggregator that computes all auto-derived stats (account age, wealth level, asset count, transaction count, goals, streaks) from existing data sources so profile reflects current reality.

### Acceptance Criteria

**ProfileStatsAggregator service:**
- [ ] File `app/profile/services/stats_aggregator.py`
- [ ] Method `aggregate(user_id)` returns dict với all stats
- [ ] **Stats computed:**
  - `account_age_days`: from user.created_at
  - `wealth_level`: from WealthLevelMapper
  - `wealth_progress`: from WealthLevelMapper
  - `asset_types_count`: distinct asset_type count from assets table (max 6)
  - `transaction_count_total`: all-time
  - `transaction_count_this_month`: current calendar month
  - `goals_active`: count goals where status="active"
  - `goals_completed`: count goals where status="completed"
  - `briefing_read_count`: from briefing_reads table
  - `current_streak`: consecutive days với activity
  - `net_worth_change_pct`: vs first recorded net worth (None if no data)

**Streak computation:**
- [ ] Helper `_compute_streak(user_id)` returns int
- [ ] "Activity" = any transaction added OR briefing read OR feedback submitted
- [ ] Streak resets if 1+ days with no activity
- [ ] Edge case: brand new user → streak = 1 (today)

**Performance:**
- [ ] Aggregator query takes <500ms even for power users với many transactions
- [ ] Use efficient aggregations (COUNT, MAX) — avoid N+1 queries
- [ ] No caching (compute on-demand to avoid stale data — per design decision)

### Test Plan

```python
async def test_aggregate_full_stats():
    user = await create_user_with_full_data()
    stats = await ProfileStatsAggregator().aggregate(user.id)
    
    assert stats["account_age_days"] == 47
    assert stats["wealth_level"]["name_vn"] in ["Khởi Đầu", "Trẻ Năng Động", "Trung Lưu Vững", "Tinh Hoa"]
    assert stats["asset_types_count"] >= 0
    assert stats["transaction_count_this_month"] >= 0
    assert stats["current_streak"] >= 1

async def test_aggregate_new_user():
    user = await create_brand_new_user()
    stats = await ProfileStatsAggregator().aggregate(user.id)
    
    assert stats["account_age_days"] == 0
    assert stats["asset_types_count"] == 0
    assert stats["transaction_count_total"] == 0
    assert stats["wealth_level"]["name_vn"] == "Khởi Đầu"  # 0 net worth
    assert stats["current_streak"] == 1  # Today counts

async def test_streak_breaks():
    user = await create_user_with_activity_pattern([
        date(2026, 5, 1),  # Activity
        date(2026, 5, 2),  # Activity
        # Skip May 3
        date(2026, 5, 4),  # Activity (broke streak)
    ])
    streak = await ProfileStatsAggregator()._compute_streak(user.id)
    assert streak == 1  # Only May 4
```

### Definition of Done

- All stats compute correctly
- Performance verified <500ms for power users
- Edge cases (new user, no activity, etc.) handled

### Labels
`phase-3.8.5` `story` `backend` `profile` `priority-critical`

---

## [Story] P3.8.5-S6: Profile view + menu integration

**Type:** Story | **Epic:** Epic 2 | **Estimate:** ~0.5 day | **Depends on:** P3.8.5-S5

### Reference
📖 [phase-3.8.5-detailed.md § 2.4, 2.5](./phase-3.8.5-detailed.md)

### Acceptance Criteria

**Profile view rendering:**
- [ ] Handler `handle_profile_view` renders comprehensive view
- [ ] Display name resolved: profile.display_name OR Telegram first_name
- [ ] Format includes:
  - Display name + level icon + level name VN
  - Level description italic
  - Account age days
  - Wealth journey: progress to next level OR "đã đạt level cao nhất"
  - Net worth change % (if data available)
  - Asset types count
  - Transactions this month
  - Goals active + completed
  - Streak days
  - Briefing read count
- [ ] Markdown formatting for emphasis
- [ ] Edit buttons at bottom: Đổi tên / Đổi tuổi / Cài thông báo / Quay lại

**Menu integration:**
- [ ] Update Phase 3.6 main menu — add "👤 Profile của tôi"
- [ ] Position: somewhere natural in menu (suggest after main 5 categories)
- [ ] Callback `menu:profile` routes to handle_profile_view

**Edge cases:**
- [ ] Brand new user (0 assets, 0 transactions) → empty stats render gracefully
- [ ] User without name in Telegram → show "Bạn" as default
- [ ] Net worth = 0 → "Khởi Đầu" with progress 0%

### Test Plan

Manual test scenarios:

```
Test 1: Mass Affluent user (Phương)
1. Login as Phương
2. /menu → Profile của tôi
3. Verify display:
   - Name: Phương 💎 Trung Lưu Vững
   - Description: Tài sản ổn định, đa dạng hóa
   - Progress to Tinh Hoa shown với amount remaining
   - 5+ asset types
   - Multiple goals
   - Streak ≥ X days

Test 2: Brand new user (Minh)
1. Login as Minh
2. Open profile
3. Verify:
   - Name: Minh 🌱 Khởi Đầu
   - Account age: 0 ngày OR 1 ngày
   - 0 asset types displayed gracefully
   - Streak: 1
```

### Definition of Done

- Profile view renders perfectly for all 4 personas (Hà, Phương, Anh Tùng, Minh)
- Menu navigation seamless
- All edit buttons functional placeholders (handlers in Epic 3)

### Labels
`phase-3.8.5` `story` `bot-handler` `profile` `priority-critical`

---

# Epic 3: User Profile (Edit)

> **Type:** Epic | **Phase:** 3.8.5 | **Day:** 4 | **Stories:** 2

## Overview

Build edit flows cho 3 fields user có thể change: display name, age range, notification settings.

## Success Definition

- ✅ User can change display name (text input)
- ✅ User can change age range (button selection)
- ✅ User can toggle briefing/reminder on/off
- ✅ User can change briefing/reminder times
- ✅ All edits reflect immediately back in profile view

## Stories

- [ ] #XXX [Story] P3.8.5-S7: Edit display name + age range flows
- [ ] #XXX [Story] P3.8.5-S8: Notification settings flow

## Reference

📖 [phase-3.8.5-detailed.md § 2.4 — Edit Flows](./phase-3.8.5-detailed.md)

### Labels
`phase-3.8.5` `epic` `profile` `priority-medium`

---

## [Story] P3.8.5-S7: Edit display name + age range flows

**Type:** Story | **Epic:** Epic 3 | **Estimate:** ~0.5 day | **Depends on:** P3.8.5-S6

### Acceptance Criteria

**Edit display name flow:**
- [ ] Tap "📝 Đổi tên hiển thị" → bot prompts for new name
- [ ] Set state "awaiting_display_name"
- [ ] Validation: 1-50 chars, no control characters
- [ ] `/cancel` exits flow gracefully
- [ ] Save updates user_profiles.display_name
- [ ] Confirms với new name, returns to profile view

**Edit age range flow:**
- [ ] Tap "🎂 Đổi nhóm tuổi" → bot shows 5 buttons: 20-29, 30-39, 40-49, 50+, "🚫 Không muốn nói"
- [ ] Select age → updates user_profiles.age_range
- [ ] "Không muốn nói" → sets age_range = NULL
- [ ] Confirms selection, returns to profile view

**Profile view refresh:**
- [ ] After any edit, refreshing profile view shows updated value
- [ ] Display name change reflects immediately in next briefing/messages

### Edge Cases

```python
# Empty name
"" → "Tên không được trống."

# Too long
"x" * 51 → "Tên dài quá! Tối đa 50 ký tự nhé."

# Special characters / SQL injection attempts
"'; DROP TABLE users; --" → Sanitize, allow but escape

# Unicode / emoji
"Phương 💚" → Allow (UTF-8 mb4)

# Telegram username with @
"@phuong" → Strip @, allow

# /cancel
"/cancel" → Clear state, return to profile view
```

### Definition of Done

- Both flows complete in real Telegram
- Edge cases handled
- Profile refreshes show new values

### Labels
`phase-3.8.5` `story` `bot-handler` `profile` `priority-medium`

---

## [Story] P3.8.5-S8: Notification settings flow

**Type:** Story | **Epic:** Epic 3 | **Estimate:** ~0.5 day | **Depends on:** P3.8.5-S6

### Acceptance Criteria

**Notification menu:**
- [ ] Tap "🔔 Cài thông báo" → shows 4 options:
  - Daily Briefing toggle (on/off)
  - Briefing time (HH:MM)
  - Reminder toggle (on/off)
  - Reminder time (HH:MM)
- [ ] Each tappable

**Toggle flows:**
- [ ] Tap briefing toggle → flips briefing_enabled, refreshes menu
- [ ] Tap reminder toggle → flips reminder_enabled, refreshes menu
- [ ] Visual indicator: "✅ Bật" vs "🔕 Tắt"

**Time change flows:**
- [ ] Tap briefing time → presets: 6:00, 7:00, 8:00, 9:00, "Tự nhập"
- [ ] "Tự nhập" → text input "HH:MM" với validation
- [ ] Same for reminder time
- [ ] Save updates respective field

**Cascade effects:**
- [ ] Briefing disabled → next morning, briefing job skips this user
- [ ] Reminder disabled → ReminderScheduler (Phase 3.8) skips this user
- [ ] Time change → next briefing/reminder uses new time

### Edge Cases

```python
# Invalid time format
"25:99" → "Giờ không hợp lệ. Format: HH:MM (00:00 - 23:59)"

# Briefing OFF then ON
- Disabled at 14:00 → 15:00 enable → Don't immediately send (wait next morning)

# Same time as another user feature
- Briefing 09:00 + Reminder 09:00 → Both should send, no collision
```

### Definition of Done

- All notification toggles functional
- Time changes persist + reflect in scheduled jobs
- Cascading behavior verified (briefing/reminder respects new settings)

### Labels
`phase-3.8.5` `story` `bot-handler` `profile` `priority-medium`

---

# 🎯 Epic Dependencies Graph

```
Epic 1 (Feedback) — independent

[Day 1-2 work]

Epic 2 (Profile View) — independent of Epic 1
Epic 3 (Profile Edit) — depends on Epic 2

[Day 3-4 work, sequential]
```

→ Epic 1 và Epic 2 có thể parallel nếu có dev support, nhưng với 1 dev (Phuong + Claude Code) → sequential.

---

# 💡 Implementation Tips

## Reuse Phase 3.7 Patterns

Active prompts pattern tương tự reminder pattern in Phase 3.8:
- Both use schedulers
- Both have cooldown + rate limit logic
- Both send Telegram messages with inline buttons

→ **Refactor opportunity:** Consider extracting `BaseScheduler` abstract class. But don't over-engineer — Phase 3.8.5 is small.

## Migration Strategy

3 migrations needed:
1. `feedbacks` table
2. `user_profiles` table  
3. `prompts_sent_log` table (for active prompt tracking)

## Testing Strategy

Phase 3.8.5 = pre-launch quality bar. Test:
- All 4 personas (Hà, Phương, Anh Tùng, Minh) on profile view
- Edge cases on feedback (empty, too long, /cancel, rate limit)
- Active prompt cooldown (don't spam)
- Wealth level boundaries (0, 30tr, 200tr, 1 tỷ exactly)

## Common Pitfalls

1. **Active prompt spam** — strict rate limit + cooldown enforcement
2. **Stale profile stats** — compute on-demand, don't cache
3. **Wealth level boundary** — `>= min AND < max` consistently
4. **Display name special chars** — UTF-8 mb4, sanitize control chars
5. **Classification errors blocking submission** — async classification, save first

---

**Phase 3.8.5 = pre-launch readiness. Sau phase này, Bé Tiền có feedback loop + user identity foundation cho soft launch tháng 6. 💚🚀**
