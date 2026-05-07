# Phase 3.8.5 — Manual Test Cases (Telegram Bot)

> **Purpose:** Comprehensive test cases for Phase 3.8.5 (Pre-Launch Readiness).  
> **Tester Profile:** No source code access. Tests via Telegram chat + Mini App.  
> **Reference:** [phase-3.8.5-detailed.md](./phase-3.8.5-detailed.md), [phase-3.8.5-issues.md](./phase-3.8.5-issues.md)

---

## 📋 How to Use This Document

### Test Case Structure

```
TC-XXX: [Title]
Type: Happy | Corner | Regression | Integration | Performance | Critical
Story: P3.8.5-Sn (links to issue)
Persona: Which test user to use
Preconditions: State required before test
Steps: Numbered actions tester performs
Expected Results: Observable outcomes (in Telegram)
Pass Criteria: All expected results met
```

### Pass / Fail Criteria

- ✅ **PASS:** All Expected Results observed
- ⚠️ **PASS WITH NOTES:** Main behavior correct, minor issues
- ❌ **FAIL:** Any Expected Result not observed
- 🚫 **BLOCKED:** Cannot execute due to dependency

---

## 🧑‍💼 Test Data Setup

**Reuse 4 personas from Phase 3.7/3.8, no new data needed for Phase 3.8.5:**

### Persona 1: Hà (Trẻ Năng Động, ~140tr)
- Account age: ~60 days
- Multiple income streams, 1 goal active, recurring patterns
- **Expected wealth level:** Trẻ Năng Động 🚀
- **Expected progress to next:** ~55% (140tr in 30-200tr range)

### Persona 2: Phương (Trung Lưu Vững, ~4.5 tỷ)
- Account age: ~90 days
- Rental property, multi-income, 2 goals
- **Expected wealth level:** Tinh Hoa 🏆 (4.5 tỷ > 1 tỷ)
- **Expected progress:** at_top = true

### Persona 3: Anh Tùng (Tinh Hoa, ~13 tỷ)
- Account age: ~120 days
- HNW user
- **Expected wealth level:** Tinh Hoa 🏆
- **Expected progress:** at_top = true

### Persona 4: Minh (Khởi Đầu, ~17tr)
- Account age: ~30 days
- Single income, no rental, no goals
- **Expected wealth level:** Khởi Đầu 🌱
- **Expected progress:** ~57% (17tr in 0-30tr range)

### Additional Test User: BrandNew
- Account age: 0 days (just created)
- 0 assets, 0 transactions, 0 goals
- **Expected wealth level:** Khởi Đầu 🌱
- **Expected progress:** 0%

---

## 🔧 Environment Requirements

- **Bot version:** Phase 3.8.5 deployed
- **Telegram client:** Mobile + Desktop
- **Database:** Personas pre-populated
- **Pre-deploy verify:** Phase 3.8 still works (regression suite)
- **Background workers running:**
  - FeedbackClassifier worker
  - PromptScheduler daily cron (9 AM)
- **YAML configs loaded:**
  - `feedback_prompts.yaml`
  - `wealth_levels.yaml`

---

## 📊 Test Coverage Overview

| Section | Test Cases | Type Distribution |
|---------|-----------|-------------------|
| Section 1: Feedback Command + Submission | 10 | Happy + Critical |
| Section 2: Auto-Classification | 5 | Integration |
| Section 3: Active Prompts | 5 | Critical + Corner |
| Section 4: Profile View | 8 | Happy + Edge |
| Section 5: Wealth Level Mapping | 5 | Happy + Boundary |
| Section 6: Profile Edit (Name + Age) | 4 | Happy + Corner |
| Section 7: Notification Settings | 4 | Happy + Integration |
| Section 8: Regression | 4 | Regression |
| **Total** | **45** | |

---

# Section 1 — Feedback Command + Submission

## TC-001: Submit feedback via /feedback command

**Type:** Happy | **Story:** P3.8.5-S1 | **Persona:** Phương

**Preconditions:**
- Bot running, Phương logged in
- No previous feedback today

**Steps:**
1. Send `/feedback`
2. Wait for bot response
3. Send: "App rất tốt nhưng tôi muốn có dark mode để dùng buổi tối"

**Expected Results:**
- Step 2 bot response:
  ```
  💌 Cảm ơn bạn muốn góp ý! Mình rất biết ơn 💚
  
  Bạn cứ chia sẻ thoải mái — bug, gợi ý, lời khen, câu hỏi, 
  hoặc bất cứ điều gì bạn nghĩ. Gõ message tiếp theo nhé.
  ```
- Step 3 bot response:
  ```
  ✅ Đã ghi nhận! Cảm ơn bạn rất nhiều 💚
  
  Team Bé Tiền sẽ review trong vòng 7 ngày. 
  Mọi feedback đều giúp sản phẩm tốt hơn cho cộng đồng.
  ```
- DB: feedback record created với content, trigger="passive_command", context filled

**Pass Criteria:**
- 2 bot messages match expected
- DB record exists
- User state cleared after submission

---

## TC-002: Feedback acknowledgment immediate (no LLM wait)

**Type:** Critical | **Story:** P3.8.5-S1 | **Persona:** Hà

**Steps:**
1. `/feedback`
2. Type: "Bot không tìm thấy tài sản của tôi"
3. Measure time from send to bot acknowledgment

**Expected Results:**
- Acknowledgment arrives <2 seconds (DOES NOT wait for classification)
- Classification happens async in background
- After ~5-10 seconds, DB record updated với category="bug", priority="high"

**Pass Criteria:**
- Acknowledgment immediate
- Classification fills in async
- User experience không lag

---

## TC-003: Empty feedback rejection

**Type:** Corner | **Story:** P3.8.5-S1 | **Persona:** Hà

**Steps:**
1. `/feedback`
2. Send empty message OR just whitespace OR very short text "ok"

**Expected Results:**
- Bot replies: "Mình chưa nhận được nội dung rõ. Gõ lại nhé hoặc /cancel để hủy."
- DB: no feedback record created
- User state still "awaiting_feedback_text" (can retry)

**Pass Criteria:**
- Validation working
- User can retry

---

## TC-004: Too long feedback rejection

**Type:** Corner | **Story:** P3.8.5-S1 | **Persona:** Hà

**Steps:**
1. `/feedback`
2. Send 5001 character message (paste long lorem ipsum)

**Expected Results:**
- Bot replies: "Feedback dài quá! Gõ ngắn gọn hơn nhé (tối đa 5000 ký tự)."
- DB: no record
- User can retry với shorter text

**Pass Criteria:**
- Length validation working
- Helpful error message

---

## TC-005: Cancel during awaiting state

**Type:** Happy | **Story:** P3.8.5-S1 | **Persona:** Hà

**Steps:**
1. `/feedback`
2. Send `/cancel` (instead of feedback content)

**Expected Results:**
- Bot replies: "OK, đã hủy. Quay lại bất cứ lúc nào với /feedback."
- User state cleared
- No DB record

**Pass Criteria:**
- /cancel respected
- Clean exit

---

## TC-006: Rate limit 5 feedbacks/day

**Type:** Critical | **Story:** P3.8.5-S1 | **Persona:** Hà

**Steps:**
1. Submit 5 feedbacks in rapid succession (`/feedback` + text × 5)
2. Try 6th feedback

**Expected Results:**
- First 5 succeed normally
- 6th: bot replies "Bạn đã gửi 5 feedback hôm nay rồi. Để tránh spam, mình giới hạn 5/ngày."
- DB: only 5 records, not 6
- Next day, limit resets

**Pass Criteria:**
- Rate limit enforced
- Clear explanation
- Counter resets daily

---

## TC-007: Context snapshot captured

**Type:** Critical | **Story:** P3.8.5-S1 | **Persona:** Phương

**Preconditions:** Phương is Trung Lưu Vững, account 90 days old, has rental + 2 goals

**Steps:**
1. Submit feedback: "Phần goals rất tốt"
2. Check DB record (tester via DB query or admin tool)

**Expected Results:**
- Feedback record context field includes:
  ```json
  {
    "wealth_level": "Trung Lưu Vững",
    "account_age_days": 90,
    "asset_types_count": 5,
    "active_features": ["rental_tracking", "goals", "recurring", "multi_income"],
    "current_phase_version": "3.8.5",
    "recent_actions": [...]
  }
  ```

**Pass Criteria:**
- Context captured automatically
- Wealth level matches user state
- Recent actions logged

---

## TC-008: /feedback while in another conversation

**Type:** Corner | **Story:** P3.8.5-S1 | **Persona:** Hà

**Preconditions:** Hà đang trong wizard add asset (set state "adding_asset")

**Steps:**
1. Send `/feedback` interrupt the wizard

**Expected Results:**
- Bot handles state transition gracefully
- Old wizard state cleared OR ask user to confirm: "Bạn đang trong giữa wizard. Hủy để gửi feedback?"
- Either approach acceptable, just don't crash

**Pass Criteria:**
- No crash
- Clear UX (either auto-cancel or confirm)

---

## TC-009: Feedback acknowledgment in Vietnamese

**Type:** Happy | **Story:** P3.8.5-S1 | **Persona:** Anh Tùng

**Steps:**
1. Submit any feedback

**Expected Results:**
- All bot messages purely tiếng Việt
- No English fallback
- Tone warm, không robotic

**Pass Criteria:**
- 100% Vietnamese
- Warm tone preserved (Bé Tiền personality)

---

## TC-010: Multiple users feedback same time

**Type:** Performance | **Story:** P3.8.5-S1 | **Personas:** Hà, Phương, Anh Tùng đồng thời

**Steps:**
1. 3 personas submit feedback simultaneously
2. Check responses + DB

**Expected Results:**
- All 3 receive acknowledgments
- All 3 DB records created
- No race conditions
- Each context snapshot specific to that user

**Pass Criteria:**
- Concurrent submission works
- No data crossover

---

# Section 2 — Auto-Classification

## TC-011: Bug classification accuracy

**Type:** Integration | **Story:** P3.8.5-S2 | **Persona:** Hà

**Steps:**
1. Submit: "Bot không trả lời khi tôi gửi /menu, đã thử 3 lần"
2. Wait 30 seconds for classification
3. Check DB record

**Expected Results:**
- category = "bug"
- priority = "high" hoặc "medium"
- confidence ≥ 0.7
- sentiment = "negative"
- classifier_version recorded

**Pass Criteria:**
- Classification matches expectation
- Confidence reasonable

---

## TC-012: Praise classification

**Type:** Integration | **Story:** P3.8.5-S2 | **Persona:** Phương

**Steps:**
1. Submit: "Bé Tiền tuyệt vời! Tôi rất thích morning briefing"
2. Wait for classification

**Expected Results:**
- category = "praise"
- sentiment = "positive"
- priority = "low" (praise is low priority for action)
- confidence ≥ 0.8

**Pass Criteria:**
- Praise correctly identified
- High confidence

---

## TC-013: Suggestion classification

**Type:** Integration | **Story:** P3.8.5-S2 | **Persona:** Hà

**Steps:**
1. Submit: "Mình muốn có dark mode để dùng buổi tối"

**Expected Results:**
- category = "suggestion"
- sentiment = "neutral" hoặc "positive"
- priority = "medium" hoặc "low"

**Pass Criteria:**
- Suggestion identified
- Reasonable priority

---

## TC-014: LLM error fallback

**Type:** Corner | **Story:** P3.8.5-S2 | **Persona:** Test admin

**Setup:** Temporarily disable DeepSeek API (or simulate error)

**Steps:**
1. Submit any feedback
2. Wait for classification cycle

**Expected Results:**
- Feedback record SAVED (acknowledgment given to user)
- Classification fields = "other"/"neutral"/"low"
- confidence = 0.0
- classifier_version = "fallback"
- Worker logs error
- Worker retries on next cycle

**Pass Criteria:**
- User flow not blocked
- Fallback values reasonable
- Retry mechanism working

---

## TC-015: Classification doesn't block other feedbacks

**Type:** Performance | **Story:** P3.8.5-S2 | **Personas:** Multiple

**Steps:**
1. Submit 10 feedbacks rapidly
2. Verify all 10 acknowledged immediately
3. Verify classification queue processes them async

**Expected Results:**
- All 10 acknowledgments < 2 seconds each
- Classification completes for all within 1-2 minutes
- Queue handles backlog

**Pass Criteria:**
- No bottleneck on submission
- Queue processes reliably

---

# Section 3 — Active Prompts

## TC-016: Day 7 prompt triggered

**Type:** Critical | **Story:** P3.8.5-S3 | **Persona:** New user "Day7User"

**Preconditions:** Create user with account_age = 7 days exactly

**Steps:**
1. Trigger daily cron (or wait for 9 AM)
2. Check Telegram

**Expected Results:**
- User receives prompt:
  ```
  💚 Bạn đã đồng hành với Bé Tiền 1 tuần rồi!
  
  Bạn cảm thấy thế nào? Có gì mình có thể cải thiện không?
  Chia sẻ cảm nhận đầu tiên nhé 🙏
  ```
- 2 buttons: [Chia sẻ cảm nhận] [Để sau]
- prompts_sent_log: record created

**Pass Criteria:**
- Prompt sent at correct trigger
- Buttons functional

---

## TC-017: User responds to prompt CTA

**Type:** Happy | **Story:** P3.8.5-S3 | **Persona:** Day7User

**Continue from TC-016:**

**Steps:**
1. Tap [Chia sẻ cảm nhận]
2. Bot prompts for feedback content
3. Type: "Mình thấy app dễ dùng nhưng cần thêm hướng dẫn ban đầu"

**Expected Results:**
- Feedback saved với trigger="post_onboarding_day_7" (NOT "passive_command")
- Acknowledgment sent
- Same flow as `/feedback` command

**Pass Criteria:**
- Trigger metadata correct
- User experience same as passive

---

## TC-018: User skips prompt

**Type:** Happy | **Story:** P3.8.5-S3 | **Persona:** Day7User

**Steps:**
1. From prompt, tap [Để sau]

**Expected Results:**
- Bot acknowledges silently or với "Hiểu rồi, mình sẽ hỏi sau nhé."
- prompts_sent_log: record với status="skipped"
- No feedback created

**Pass Criteria:**
- Skip respected
- No further nag

---

## TC-019: Cooldown prevents re-prompt

**Type:** Critical | **Story:** P3.8.5-S3 | **Persona:** Day7User

**Continue from TC-016 (prompt sent today)**

**Steps:**
1. Try to manually re-trigger prompt (or simulate user reaching trigger again next day)
2. Check if prompt re-sent

**Expected Results:**
- Cooldown active (60 days for post_onboarding_day_7)
- Bot does NOT re-send
- No new entry in prompts_sent_log

**Pass Criteria:**
- Cooldown logic works
- No duplicate prompts within window

---

## TC-020: Max 2 prompts per month rate limit

**Type:** Critical | **Story:** P3.8.5-S3 | **Persona:** PowerUser (multiple triggers met)

**Setup:** Create user with multiple triggers met simultaneously:
- account_age = 90 (post_3_months_active)
- briefing_read_count = 30 (post_briefing_30_reads)
- goals_completed_count = 1 (post_first_goal_completed)

**Steps:**
1. Run scheduler check_and_send_prompts
2. Verify only 2 prompts sent (not 3)
3. Wait 30 days, run again

**Expected Results:**
- First run: 2 prompts sent (highest priority first)
- Third trigger met but BLOCKED by rate limit
- 30 days later: 3rd prompt eligible to send

**Pass Criteria:**
- Hard limit 2/month enforced
- No spam even if multiple triggers

---

# Section 4 — Profile View

## TC-021: View profile — Phương (Tinh Hoa)

**Type:** Happy | **Story:** P3.8.5-S6 | **Persona:** Phương (~4.5 tỷ)

**Steps:**
1. `/menu` → tap "👤 Profile của tôi"

**Expected Results:**
- Display:
  ```
  👤 **Phương** 🏆 Tinh Hoa
  _Tài sản đáng kể, cần quản lý chuyên sâu_
  
  💚 Đồng hành cùng Bé Tiền **90 ngày**
  
  📈 **Hành trình tài sản:**
  🏆 Bạn đã đạt level cao nhất!
  
  📊 **Hoạt động:**
  • 5 loại tài sản đang theo dõi
  • [N] giao dịch tháng này
  • 2 mục tiêu đang theo đuổi
  
  🔥 **Streak hiện tại:** [X] ngày liên tiếp
  📅 **Daily briefing:** đã đọc [N] lần
  ```
- Edit buttons at bottom

**Pass Criteria:**
- Tinh Hoa level shown correctly
- "At top" message
- All stats accurate
- Vietnamese only

---

## TC-022: View profile — Hà (Trẻ Năng Động)

**Type:** Happy | **Story:** P3.8.5-S6 | **Persona:** Hà (~140tr)

**Steps:**
1. Open profile

**Expected Results:**
- Level: 🚀 Trẻ Năng Động
- Description: "Đang xây dựng tài sản, năng động"
- Progress section:
  - "Tiến độ tới Trung Lưu Vững: ~55%"
  - "Còn cần: ~60tr"
- Net worth change %: shown if data available

**Pass Criteria:**
- Correct tier
- Progress calculation accurate
- Amount-to-next correct

---

## TC-023: View profile — Minh (Khởi Đầu)

**Type:** Happy | **Story:** P3.8.5-S6 | **Persona:** Minh (~17tr)

**Steps:**
1. Open profile

**Expected Results:**
- Level: 🌱 Khởi Đầu
- Progress: ~57% (17/30 tr)
- Còn cần: 13tr to Trẻ Năng Động
- Stats sparse (1 income stream, 0 goals)

**Pass Criteria:**
- Khởi Đầu correctly shown
- Progress reasonable
- Empty states handled

---

## TC-024: View profile — Brand new user

**Type:** Corner | **Story:** P3.8.5-S6 | **Persona:** BrandNew (just created)

**Steps:**
1. Just create new account
2. Open profile immediately

**Expected Results:**
- Level: 🌱 Khởi Đầu
- Account age: 0 ngày OR "Vừa bắt đầu hôm nay"
- Progress: 0%
- 0 asset types
- 0 transactions
- 0 goals
- Streak: 1 (today counts)
- Briefing read: 0
- Net worth change: not shown (no first record)

**Pass Criteria:**
- Empty state graceful
- No errors / null displays
- Encouraging tone (not "you have nothing")

---

## TC-025: Display name override Telegram

**Type:** Happy | **Story:** P3.8.5-S6 | **Persona:** Hà

**Preconditions:** Hà set display_name = "Hà-Bé-Tiền-Fan" (will test in TC-029)

**Steps:**
1. Open profile

**Expected Results:**
- Header shows display_name "Hà-Bé-Tiền-Fan", NOT Telegram first_name "Hà"

**Pass Criteria:**
- Override works
- Profile uses display_name preferentially

---

## TC-026: Display name fallback to Telegram

**Type:** Happy | **Story:** P3.8.5-S6 | **Persona:** New user without display_name set

**Steps:**
1. Open profile

**Expected Results:**
- Header shows Telegram first_name
- If no Telegram name: "Bạn"

**Pass Criteria:**
- Fallback chain works

---

## TC-027: Streak reflects actual activity

**Type:** Integration | **Story:** P3.8.5-S5 | **Persona:** Hà

**Steps:**
1. Note current streak in profile (e.g., 15 days)
2. Skip activity for 1 day (don't read briefing, don't add tx)
3. Open profile next day

**Expected Results:**
- Streak resets to 1 (broke streak)
- (Note: streak day "today" only counts if activity today)

**Pass Criteria:**
- Streak logic accurate
- Reflects real activity

---

## TC-028: Performance — large user profile

**Type:** Performance | **Story:** P3.8.5-S5 | **Persona:** Anh Tùng (heaviest data)

**Steps:**
1. Open profile (Anh Tùng has 13 tỷ, 3 BĐS, ~200 transactions)
2. Measure response time

**Expected Results:**
- Profile rendered within 2 seconds
- All stats computed correctly
- No timeout

**Pass Criteria:**
- <2s response
- Accuracy maintained

---

# Section 5 — Wealth Level Mapping

## TC-029: Boundary 0 → Khởi Đầu

**Type:** Boundary | **Story:** P3.8.5-S4 | **Persona:** BrandNew (0đ)

**Expected Results:**
- net_worth = 0 → Khởi Đầu 🌱
- progress_to_next = 0%

**Pass Criteria:**
- 0 boundary handled

---

## TC-030: Boundary 30tr → Trẻ Năng Động (next tier)

**Type:** Boundary | **Story:** P3.8.5-S4 | **Setup:** Test user with exactly 30,000,000đ net worth

**Expected Results:**
- Level: Trẻ Năng Động (NOT Khởi Đầu)
- Logic: `>= 30tr AND < 200tr`

**Pass Criteria:**
- Boundary exclusive on lower tier, inclusive on this tier

---

## TC-031: Boundary 200tr → Trung Lưu Vững

**Type:** Boundary | **Story:** P3.8.5-S4 | **Setup:** Test user with 200,000,000đ exactly

**Expected Results:**
- Level: Trung Lưu Vững 💎

**Pass Criteria:**
- Boundary correct

---

## TC-032: Boundary 1 tỷ → Tinh Hoa

**Type:** Boundary | **Story:** P3.8.5-S4 | **Setup:** Test user with 1,000,000,000đ exactly

**Expected Results:**
- Level: Tinh Hoa 🏆
- Progress: at_top = true

**Pass Criteria:**
- Top tier boundary correct

---

## TC-033: Net worth change shows correctly

**Type:** Integration | **Story:** P3.8.5-S5 | **Persona:** Hà

**Preconditions:** Hà's first recorded net worth was 100tr, now 140tr

**Expected Results:**
- net_worth_change_pct = +40%
- Profile shows: "Net worth thay đổi từ khi bắt đầu: +40.0%"

**Pass Criteria:**
- Calculation correct
- Sign (+/-) shown

---

# Section 6 — Profile Edit (Name + Age)

## TC-034: Change display name happy path

**Type:** Happy | **Story:** P3.8.5-S7 | **Persona:** Hà

**Steps:**
1. Open profile → tap "📝 Đổi tên hiển thị"
2. Bot prompts for name
3. Type "Hà-Bé-Tiền-Fan"

**Expected Results:**
- Bot confirms: "✅ Đã đổi tên hiển thị thành: **Hà-Bé-Tiền-Fan**"
- Profile view refreshes với new name
- DB user_profiles.display_name updated

**Pass Criteria:**
- Edit working
- Confirmation clear
- Profile reflects change

---

## TC-035: Display name validation

**Type:** Corner | **Story:** P3.8.5-S7 | **Persona:** Hà

**Steps:**
1. Try invalid inputs:
   - Empty: ""
   - 51 chars: "x" * 51
   - Special: "Phương 💚 ❤️" (emoji)
   - Telegram username: "@phuong"

**Expected Results:**
- Empty → "Tên không được trống"
- 51 chars → "Tên dài quá! Tối đa 50 ký tự"
- Emoji → ACCEPTED (UTF-8 mb4)
- @phuong → may strip @ or accept as-is (both OK)

**Pass Criteria:**
- Validation messages clear
- Edge cases handled

---

## TC-036: Change age range

**Type:** Happy | **Story:** P3.8.5-S7 | **Persona:** Phương

**Steps:**
1. Profile → "🎂 Đổi nhóm tuổi"
2. Select "30-39"

**Expected Results:**
- Confirmation: "Đã cập nhật nhóm tuổi: 30-39"
- DB: age_range = "30-39"
- Note: age_range NOT shown in profile view by default (privacy), only used for personalization internally

**Pass Criteria:**
- Selection saved
- DB updated

---

## TC-037: "Không muốn nói" age option

**Type:** Happy | **Story:** P3.8.5-S7 | **Persona:** Hà

**Steps:**
1. Profile → 🎂 → tap "🚫 Không muốn nói"

**Expected Results:**
- DB: age_range = NULL
- Confirmation respects choice

**Pass Criteria:**
- Privacy respected
- NULL accepted in DB

---

# Section 7 — Notification Settings

## TC-038: View notification settings

**Type:** Happy | **Story:** P3.8.5-S8 | **Persona:** Hà

**Steps:**
1. Profile → "🔔 Cài thông báo"

**Expected Results:**
- Display 4 options:
  - 📅 Daily Briefing: ✅ Bật
  - ⏰ Briefing time: 07:00
  - ⏰ Reminder: ✅ Bật
  - ⏰ Reminder time: 09:00

**Pass Criteria:**
- Current state visible
- Toggleable

---

## TC-039: Disable briefing

**Type:** Integration | **Story:** P3.8.5-S8 | **Persona:** Hà

**Steps:**
1. Notification settings → tap "📅 Daily Briefing: ✅ Bật"
2. Toggle to OFF
3. Wait until next morning

**Expected Results:**
- DB: briefing_enabled = false
- Setting refreshes to "🔕 Tắt"
- Next morning: NO briefing sent to Hà
- Other users still receive briefing normally

**Pass Criteria:**
- Toggle persistent
- Cron job respects setting

---

## TC-040: Change briefing time

**Type:** Integration | **Story:** P3.8.5-S8 | **Persona:** Phương

**Steps:**
1. Notification settings → "⏰ Briefing time: 07:00"
2. Tap → presets shown
3. Select "08:00"

**Expected Results:**
- DB: briefing_time = "08:00"
- Confirmation shown
- Next morning: briefing sent at 08:00 (not 07:00)

**Pass Criteria:**
- Time updated
- Schedule respects new time

---

## TC-041: Custom time entry

**Type:** Happy | **Story:** P3.8.5-S8 | **Persona:** Phương

**Steps:**
1. Briefing time presets → tap "Tự nhập"
2. Enter "06:30"

**Expected Results:**
- Validation passes (HH:MM format)
- DB: briefing_time = "06:30"
- Invalid input "25:99" → "Giờ không hợp lệ. Format: HH:MM"

**Pass Criteria:**
- Custom times work
- Validation correct

---

# Section 8 — Regression

## TC-042: Phase 3.8 features still work

**Type:** Regression | **Story:** P3.8 (regression) | **Persona:** Phương

**Steps:**
1. Test Phase 3.8 critical flows:
   - Add rental property
   - Get reminder for recurring expense
   - Forecast cashflow
   - View goals

**Expected Results:**
- All Phase 3.8 features functional
- No new errors after Phase 3.8.5 deploy

**Pass Criteria:**
- 4/4 Phase 3.8 features OK
- No regression

---

## TC-043: Phase 3.7 agent still works

**Type:** Regression | **Story:** P3.7 (regression) | **Persona:** Hà

**Steps:**
1. Send free-form queries:
   - "Tài sản của tôi"
   - "Thu nhập thụ động"
   - "Mã chứng khoán nào đang lãi" (the famous bug fix)

**Expected Results:**
- All queries work
- The "đang lãi" bug fix preserved (only winners returned)

**Pass Criteria:**
- Phase 3.7 stays solid
- No agent regression

---

## TC-044: Phase 3.6 menu intact

**Type:** Regression | **Story:** P3.6 (regression) | **Persona:** Hà

**Steps:**
1. `/menu` → verify all 5 categories work
2. NEW: "👤 Profile của tôi" added correctly

**Expected Results:**
- Original 5 categories still there
- New Profile item added
- Navigation seamless

**Pass Criteria:**
- Menu integration clean
- No layout broken

---

## TC-045: Onboarding flow not broken

**Type:** Regression | **Story:** P1/P2 (regression) | **Persona:** New user

**Steps:**
1. Create completely new user
2. Go through onboarding
3. After 7 days: should receive prompt (TC-016 verified)

**Expected Results:**
- Onboarding flow works
- New user can use feedback + profile from Day 1
- Day 7 prompt triggers correctly

**Pass Criteria:**
- New user experience smooth
- Phase 3.8.5 features integrate from Day 1

---

# 📋 Test Execution Sheet Template

```
| TC ID | Title | Type | Status | Tester | Date | Notes |
|-------|-------|------|--------|--------|------|-------|
| TC-001 | Submit feedback | Happy | _____ | _____ | _____ | _____ |
| TC-016 | Day 7 prompt | Critical | _____ | _____ | _____ | _____ |
| TC-029-032 | Wealth boundaries | Boundary | _____ | _____ | _____ | _____ |
| TC-042 | Phase 3.8 regression | Regression | _____ | _____ | _____ | _____ |
... 
```

**Status values:** ✅ PASS, ⚠️ PASS WITH NOTES, ❌ FAIL, 🚫 BLOCKED, ⏭ SKIPPED

---

# 🎯 Phase 3.8.5 Exit Criteria Verification

After all test cases, verify:

| Criterion | Section | Critical TCs |
|-----------|---------|--------------|
| Feedback command working | Section 1 | TC-001 (submit), TC-006 (rate limit) |
| Auto-classification ≥80% accuracy | Section 2 | TC-011, TC-012 (multiple types) |
| Active prompts (post-events) | Section 3 | TC-016 (Day 7), TC-020 (rate limit) |
| Profile view comprehensive | Section 4 | TC-021 (Phương), TC-024 (BrandNew) |
| Wealth levels VN correct | Section 5 | TC-029-032 (all 4 boundaries) |
| Edit flows working | Section 6, 7 | TC-034 (name), TC-040 (time) |
| No regressions | Section 8 | TC-042, TC-043, TC-044 |

**🚨 Critical tests:**
- TC-002 (acknowledgment immediate, no LLM wait)
- TC-016 (active prompt sent at trigger)
- TC-020 (max 2/month rate limit hard cap)
- TC-029-032 (wealth level boundaries — 4 tests)
- TC-042 (Phase 3.8 not broken)

If ALL critical PASS → ✅ Ready for soft launch tháng 6.

---

# 🐛 Common Failure Modes — What to Watch

## 1. Active Prompt Spam
**Symptom:** User receives 3+ prompts in 1 week.  
**Cause:** Cooldown logic or rate limit broken.  
**Action:** Verify cooldown_days enforcement + max 2/month hard cap.

## 2. Feedback Submission Slow
**Symptom:** User waits 5+ seconds for acknowledgment.  
**Cause:** Classification synchronous in submit flow.  
**Action:** Save first, classify async via queue.

## 3. Profile Stats Stale
**Symptom:** User added asset but profile doesn't update.  
**Cause:** Caching or async refresh issue.  
**Action:** Compute on-demand. No caching.

## 4. Wealth Level Off-By-One
**Symptom:** User với 30tr exactly shown as Khởi Đầu (should be Trẻ Năng Động).  
**Cause:** Boundary `<=` vs `<` confusion.  
**Action:** Use `>= min AND < max` consistently.

## 5. Display Name Crashes With Special Chars
**Symptom:** Emoji name → 500 error.  
**Cause:** DB column not UTF-8 mb4.  
**Action:** Verify migration uses `utf8mb4_unicode_ci`.

## 6. Notification Time Change Doesn't Apply
**Symptom:** User changed briefing to 8:00 but still receives at 7:00.  
**Cause:** Cron job reads stale config.  
**Action:** Job should query DB each run, not cache config.

---

# 📊 Test Coverage Summary

```
Total test cases: 45

By Section:
  S1 Feedback Command:        10 cases (TC-001 to TC-010)
  S2 Auto-Classification:      5 cases (TC-011 to TC-015)
  S3 Active Prompts:           5 cases (TC-016 to TC-020)
  S4 Profile View:             8 cases (TC-021 to TC-028)
  S5 Wealth Level Mapping:     5 cases (TC-029 to TC-033)
  S6 Profile Edit (Name/Age):  4 cases (TC-034 to TC-037)
  S7 Notification Settings:    4 cases (TC-038 to TC-041)
  S8 Regression:               4 cases (TC-042 to TC-045)

By Type:
  Happy:               ~22 cases (49%)
  Critical:             ~5 cases (11%)
  Integration:          ~6 cases (13%)
  Corner:               ~3 cases (7%)
  Boundary:             ~4 cases (9%)
  Performance:          ~2 cases (4%)
  Regression:           ~3 cases (7%)
```

---

# 🚀 Final Notes for Tester

## Before Testing
1. Read `phase-3.8.5-detailed.md` để hiểu 2 components
2. Read `phase-3.8.5-issues.md` cho context per story
3. Verify background workers running:
   - FeedbackClassifier worker
   - PromptScheduler daily cron
4. YAML configs loaded:
   - feedback_prompts.yaml (5 prompts)
   - wealth_levels.yaml (4 levels)
5. 4 personas + BrandNew user setup

## During Testing — Order Matters

1. **Section 1 first** (feedback foundation)
2. **Section 2** (classification — needs feedback data from Section 1)
3. **Section 3** (active prompts — separate trigger flow)
4. **Section 4 + 5** (profile view + wealth — independent)
5. **Section 6 + 7** (edit flows — depends on Section 4)
6. **Section 8** (regression — must pass)

## CRITICAL Tests You CANNOT Skip

| TC | Why Critical |
|----|--------------|
| **TC-002** | Acknowledgment speed — UX critical |
| **TC-006** | Rate limit prevents spam |
| **TC-016** | Active prompt actually triggers |
| **TC-020** | Max 2/month hard cap |
| **TC-029-032** | Wealth level boundaries |
| **TC-042-044** | No regression in earlier phases |

If ANY critical fails, **iterate before ship**.

---

**Phase 3.8.5 = pre-launch readiness. Pass all → ready for soft launch tháng 6/2026 với feedback loop + user identity foundation. 💚🚀**
