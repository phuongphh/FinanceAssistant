# Phase 4.1 — Manual Test Cases

> **Total estimate:** ~120 test cases across 13 stories + cross-cutting concerns
> **Format:** Mỗi TC có Setup → Steps → Expected → Signoff marker
> **Signoff:** `[unsigned]` mặc định; operator/QA đổi thành `[signed: name-date]` khi pass
> **Persona:** Test cases reference 5 personas dưới đây để biến test real-world.

---

## 🎭 Test Personas

Các persona dùng để run E2E và edge cases. Tạo trên staging với data thật.

### P1 — Linh, 32, Marketing Manager, Hà Nội
- Wealth: ~250tr (tiết kiệm + cổ phiếu)
- Tech-savvy mức trung bình, dùng Telegram cho crypto
- Goal: hiểu rõ tổng tài sản trước khi tính chuyện mua nhà
- Inferred segment: `young_pro`

### P2 — Anh Tuấn, 41, Senior Engineer, TP.HCM
- Wealth: ~1.8 tỷ (chứng khoán + nhà đất + crypto)
- Tech expert, dùng Telegram nhiều
- Goal: lên kế hoạch nghỉ hưu sớm (FIRE)
- Inferred segment: `mass_affluent`

### P3 — Chị Hương, 38, Doanh nhân, Đà Nẵng
- Wealth: ~6.5 tỷ (kinh doanh + bất động sản)
- Tech mức cơ bản, ít dùng Telegram
- Goal: theo dõi chi tiêu doanh nghiệp vs cá nhân
- Inferred segment: `hnw`

### P4 — Minh, 28, Junior Developer, Hà Nội
- Wealth: ~60tr (mới tích lũy)
- Tech expert, dùng nhiều messaging app
- Goal: theo dõi chi tiêu, học cách đầu tư
- Inferred segment: `starter`

### P5 — Anh Khải, 45, Manager Tài chính, Hải Phòng
- Wealth: ~3.2 tỷ
- Skeptical về AI tài chính, dùng Telegram cho công việc
- Goal: muốn challenge sản phẩm, không dễ wow
- Inferred segment: `mass_affluent`

---

## 📋 Test Case Status Summary

| Story | TC Count | Signed | Unsigned |
|---|---|---|---|
| A.1 Onboarding | 20 | 0 | 20 |
| A.2 First-Twin + A.8 First briefing | 20 | 0 | 20 |
| A.3 Cost guardrail + A.4 Daily cost report | 20 | 0 | 20 |
| A.5 Sentry + A.6 KPI digest + A.7 Feedback triage | 20 | 0 | 20 |
| B.1 Share image + B.2 Calibration + C.1 Invite + C.4 Founding | 20 | 0 | 20 |
| Cross-cutting (regression, security, performance, persona, contract) | 20 | 0 | 20 |
| **Total** | **120** | **0** | **120** |

---

## 🧪 BATCH 1 — Story A.1 Onboarding Redesign (TC001–TC020)

### TC001 — `/start` lần đầu, không invite code

**Story:** A.1 | **Type:** Happy Path | **Priority:** P0 | **Persona:** P1

**Setup:**
- Clean Telegram account
- Bot deployed với `ONBOARDING_V2_ENABLED=true`
- User chưa từng dùng Bé Tiền

**Steps:**
1. User send `/start` (không kèm payload invite)
2. Quan sát response từ bot

**Expected:**
- Bot phản hồi message < 200 chars giới thiệu Bé Tiền
- Inline button "🌱 Bắt đầu hành trình" xuất hiện dưới message
- Row mới trong `onboarding_sessions` với `current_step='goal_question'` (chưa active state machine cho đến khi user bấm button)
- KHÔNG có row nào trong `users.acquisition_source` (vì không invite)

**Signoff:** [unsigned]

---

### TC002 — `/start` với invite code hợp lệ (source: friends)

**Story:** A.1 + C.1 | **Type:** Happy Path | **Priority:** P0 | **Persona:** P1

**Setup:**
- Generate 1 invite code qua `scripts/soft_launch_acquisition.py` với `source='friends'`, `grants_founding_status=TRUE`
- Clean user

**Steps:**
1. User send `/start invite_<token>`
2. Quan sát response

**Expected:**
- Welcome message variant `friends` với placeholder `{referrer_name}` đã được substitute (nếu yaml config sẵn)
- `users.acquisition_source = 'friends'`
- `users.is_founding_member = TRUE`
- `users.founding_member_sequence = 1` (nếu là user đầu)
- `users.founding_member_at = NOW()`
- Founding banner xuất hiện trong welcome message
- Inline button "🌱 Bắt đầu hành trình" có

**Signoff:** [unsigned]

---

### TC003 — `/start` với invite code đã expire/đã dùng

**Story:** A.1 + C.1 | **Type:** Corner Case | **Priority:** P0 | **Persona:** P4

**Setup:**
- Invite code đã có user khác redeem trước đó (`invite_codes.redeemed_at IS NOT NULL`)

**Steps:**
1. User mới send `/start invite_<same_token>`

**Expected:**
- Bot phản hồi message lịch sự: *"Mã mời này đã được sử dụng. Bạn vẫn có thể thử Bé Tiền — bấm vào đây để bắt đầu."*
- Inline button "🌱 Bắt đầu hành trình" có
- `users.acquisition_source = NULL` hoặc `'expired_invite'`
- `users.is_founding_member = FALSE` (KHÔNG được hưởng founding status)
- Operator log warning cảnh báo về duplicate invite use

**Signoff:** [unsigned]

---

### TC004 — Bấm "Bắt đầu hành trình" → Step 1 hiển thị Goal question

**Story:** A.1 | **Type:** Happy Path | **Priority:** P0 | **Persona:** P1

**Setup:**
- User đã /start, đang ở welcome screen

**Steps:**
1. User bấm "🌱 Bắt đầu hành trình"

**Expected:**
- Bot send message với prefix `(1/3)`
- Nội dung câu hỏi: *"Để Bé Tiền hiểu bạn hơn — bạn muốn Bé Tiền giúp gì trước nhất?"*
- 3 inline button hiển thị đúng emoji + text:
  - 🌱 Hiểu rõ tổng tài sản của tôi
  - 🎯 Lên kế hoạch cho mục tiêu lớn
  - 📊 Theo dõi chi tiêu thông minh
- `onboarding_sessions.current_step = 'goal_question'`, `started_at = NOW()`

**Signoff:** [unsigned]

---

### TC005 — Chọn Goal "Hiểu rõ tổng tài sản" → Step 2 hiển thị

**Story:** A.1 | **Type:** Happy Path | **Priority:** P0 | **Persona:** P1

**Setup:**
- Đang ở Step 1 sau TC004

**Steps:**
1. Bấm button 🌱 "Hiểu rõ tổng tài sản của tôi"

**Expected:**
- Bot send message với prefix `(2/3)`
- Prompt nhập số tiền tổng tiết kiệm + đầu tư hiện tại
- Hint format: *"Bạn có thể nhập tự do, ví dụ '300 triệu' hoặc '1.5 tỷ' — Bé Tiền hiểu được"*
- Inline button "🤖 Để Bé Tiền dùng demo trước" có
- `onboarding_sessions.goal_choice = 'understand_wealth'`
- `onboarding_sessions.current_step = 'first_asset'`

**Signoff:** [unsigned]

---

### TC006 — Chọn Goal "Lên kế hoạch mục tiêu lớn"

**Story:** A.1 | **Type:** Happy Path | **Priority:** P1 | **Persona:** P2

**Setup:** Same as TC004

**Steps:**
1. Bấm button 🎯 "Lên kế hoạch cho mục tiêu lớn"

**Expected:**
- Bot move sang Step 2 (giống TC005)
- `onboarding_sessions.goal_choice = 'plan_goal'`
- (Optional, nếu Step 2 personalize theo goal): copy step 2 nhẹ nhàng nhắc đến "mục tiêu lớn" — vd: *"Để Bé Tiền giúp bạn lên kế hoạch, hãy cho biết bạn đang có bao nhiêu..."*

**Signoff:** [unsigned]

---

### TC007 — Chọn Goal "Theo dõi chi tiêu thông minh"

**Story:** A.1 | **Type:** Happy Path | **Priority:** P1 | **Persona:** P4

**Setup:** Same as TC004

**Steps:**
1. Bấm button 📊 "Theo dõi chi tiêu thông minh"

**Expected:**
- Bot move sang Step 2
- `onboarding_sessions.goal_choice = 'track_spending'`

**Signoff:** [unsigned]

---

### TC008 — Nhập asset "300 triệu" — wealth inference young_pro

**Story:** A.1 | **Type:** Happy Path | **Priority:** P0 | **Persona:** P1

**Setup:**
- Đang ở Step 2

**Steps:**
1. User gõ tin nhắn: `300 triệu`
2. Quan sát phản hồi

**Expected:**
- Bot acknowledge: *"Bé Tiền ghi nhận: 300.000.000đ"* (format VND chuẩn)
- `onboarding_sessions.inferred_wealth_segment = 'young_pro'` (100tr–500tr bucket)
- `onboarding_sessions.current_step = 'twin_shown'`
- Asset record được tạo trong `assets` table với user_id + amount
- Trigger Twin computation (sang TC013)

**Signoff:** [unsigned]

---

### TC009 — Nhập asset "1.5 tỷ" — wealth inference mass_affluent

**Story:** A.1 | **Type:** Happy Path | **Priority:** P0 | **Persona:** P2

**Setup:** Đang ở Step 2

**Steps:**
1. User gõ: `1.5 tỷ`

**Expected:**
- Bot acknowledge: *"Bé Tiền ghi nhận: 1.500.000.000đ"*
- `inferred_wealth_segment = 'mass_affluent'` (500tr–5 tỷ bucket)

**Signoff:** [unsigned]

---

### TC010 — Nhập asset "50 triệu" — wealth inference starter

**Story:** A.1 | **Type:** Happy Path | **Priority:** P1 | **Persona:** P4

**Steps:**
1. User gõ: `50tr`

**Expected:**
- Bé Tiền parse "50tr" thành 50.000.000đ
- `inferred_wealth_segment = 'starter'` (< 100tr)

**Signoff:** [unsigned]

---

### TC011 — Nhập asset "8 tỷ" — wealth inference hnw

**Story:** A.1 | **Type:** Happy Path | **Priority:** P1 | **Persona:** P3

**Steps:**
1. User gõ: `8 tỷ`

**Expected:**
- `inferred_wealth_segment = 'hnw'` (> 5 tỷ)
- Twin computation vẫn chạy bình thường (không có gating theo segment ở Phase 4.1)

**Signoff:** [unsigned]

---

### TC012 — Nhập asset rác / không parse được

**Story:** A.1 | **Type:** Corner Case | **Priority:** P0 | **Persona:** P4

**Steps:**
1. User gõ: `hi Bé Tiền` (không có số)

**Expected:**
- Bot không assume số → phản hồi nhẹ nhàng: *"Bé Tiền chưa hiểu số tiền — bạn nhập lại giúp Bé Tiền nhé, ví dụ '300 triệu' hoặc '1.5 tỷ'"*
- KHÔNG advance state machine — vẫn ở `current_step = 'first_asset'`
- KHÔNG tạo asset row

**Signoff:** [unsigned]

---

### TC013 — Bấm "Để Bé Tiền dùng demo trước" → Demo mode banner

**Story:** A.1 | **Type:** Happy Path | **Priority:** P0 | **Persona:** P5

**Setup:** Đang ở Step 2

**Steps:**
1. Bấm button "🤖 Để Bé Tiền dùng demo trước"

**Expected:**
- Bot send message với banner:
  > 📌 Demo Mode — đây là Twin của một người giả định với 50 triệu tiết kiệm. Twin của bạn sẽ khác — nhập tài sản thật để xem Twin riêng của bạn.
- Sau banner, tiếp tục Twin reveal flow với data placeholder 50tr
- `onboarding_sessions.inferred_wealth_segment = NULL` (chưa biết segment thật)
- Asset placeholder KHÔNG persist vào `assets` table chính (chỉ ephemeral để render Twin)
- Sau khi xem demo, button "💎 Xem Twin của tôi" hiện ra → bấm vào quay lại Step 2

**Signoff:** [unsigned]

---

### TC014 — Sau Demo Mode, bấm "Xem Twin của tôi" → quay lại Step 2

**Story:** A.1 | **Type:** Happy Path | **Priority:** P0 | **Persona:** P5

**Setup:**
- Vừa xem Twin demo từ TC013

**Steps:**
1. Bấm button "💎 Xem Twin của tôi"

**Expected:**
- Bot quay lại Step 2 prompt nhập asset thật
- Copy có thể adapt: *"Tốt — bây giờ cho Bé Tiền biết tài sản thật của bạn nhé"*
- `onboarding_sessions.current_step = 'first_asset'` (rewind)

**Signoff:** [unsigned]

---

### TC015 — Hardcoded Vietnamese strings — vi-localization-checker

**Story:** A.1 | **Type:** Contract Check | **Priority:** P0

**Setup:** Code base sau khi A.1 ship

**Steps:**
1. Chạy agent `vi-localization-checker` trên `bot/handlers/start_handler.py` + `services/onboarding/*`

**Expected:**
- Agent pass: KHÔNG có hardcoded Vietnamese string trong code
- Tất cả copy nằm trong `content/onboarding/welcome_v2.yaml` hoặc `demo_mode_framing.yaml`

**Signoff:** [unsigned]

---

### TC016 — Source-aware welcome copy — variant `friends`

**Story:** A.1 + C.1 | **Type:** Happy Path | **Priority:** P1 | **Persona:** P1

**Setup:**
- Invite code với `source='friends'` và metadata có `referrer_name='Linh'`

**Steps:**
1. User redeem invite → welcome message

**Expected:**
- Welcome copy có substring: *"Linh giới thiệu bạn đến với Bé Tiền"*
- Tone ấm áp (không formal-business)

**Signoff:** [unsigned]

---

### TC017 — Source-aware welcome copy — variant `vn_finance_community`

**Story:** A.1 + C.1 | **Type:** Happy Path | **Priority:** P1 | **Persona:** P2

**Setup:** Invite code `source='vn_finance_community'`

**Steps:**
1. User redeem → welcome

**Expected:**
- Welcome copy có substring: *"Cảm ơn bạn đến từ cộng đồng tài chính"*
- Tone professional, mention 3 thứ Bé Tiền làm khác (briefing, Twin, chat 1-1)
- KHÔNG có placeholder `{referrer_name}` (vì variant này không cần)

**Signoff:** [unsigned]

---

### TC018 — `/start` lại khi đang giữa onboarding chưa xong

**Story:** A.1 | **Type:** Corner Case | **Priority:** P1 | **Persona:** P4

**Setup:**
- User đang ở Step 2 (chưa hoàn tất)

**Steps:**
1. User gõ `/start` lần nữa

**Expected:**
- Bot phản hồi: *"Bạn đang ở bước 2/3 — Bé Tiền giữ chỗ giúp bạn. Tiếp tục hay bắt đầu lại?"*
- 2 inline button: "▶️ Tiếp tục" / "🔄 Bắt đầu lại"
- Nếu chọn Tiếp tục → quay lại Step 2 với prompt y nguyên
- Nếu chọn Bắt đầu lại → reset `onboarding_sessions`, quay lại Step 1

**Signoff:** [unsigned]

---

### TC019 — User cũ (tạo trước phase_4_1_deploy_date) gõ `/start`

**Story:** A.1 | **Type:** Regression | **Priority:** P0 | **Persona:** P2

**Setup:**
- Tạo user trên staging với `users.created_at = phase_4_1_deploy_date - 1 day`
- `ONBOARDING_V2_ENABLED=true`

**Steps:**
1. User gõ `/start`

**Expected:**
- User cũ KHÔNG bị qua flow mới
- Bot phản hồi với flow cũ (welcome message từ Phase 4A/4B)
- KHÔNG tạo row mới trong `onboarding_sessions`
- Verify qua `users.created_at < phase_4_1_deploy_date` check trong handler

**Signoff:** [unsigned]

---

### TC020 — Feature flag `ONBOARDING_V2_ENABLED=false` rollback

**Story:** A.1 | **Type:** Rollback Test | **Priority:** P0 | **Persona:** P1

**Setup:**
- Toggle ENV `ONBOARDING_V2_ENABLED=false`
- Restart bot

**Steps:**
1. Clean user gõ `/start`

**Expected:**
- Bot fallback sang flow cũ (Phase 4A/4B onboarding)
- KHÔNG render 3-step flow mới
- KHÔNG có row trong `onboarding_sessions`
- Existing user của Phase 4.1 (đã onboard qua v2) vẫn dùng được — không break data

**Signoff:** [unsigned]

---

## 📊 Batch 1 Summary

| TC | Type | Priority | Status |
|---|---|---|---|
| TC001 | Happy Path | P0 | [unsigned] |
| TC002 | Happy Path | P0 | [unsigned] |
| TC003 | Corner Case | P0 | [unsigned] |
| TC004 | Happy Path | P0 | [unsigned] |
| TC005 | Happy Path | P0 | [unsigned] |
| TC006 | Happy Path | P1 | [unsigned] |
| TC007 | Happy Path | P1 | [unsigned] |
| TC008 | Happy Path | P0 | [unsigned] |
| TC009 | Happy Path | P0 | [unsigned] |
| TC010 | Happy Path | P1 | [unsigned] |
| TC011 | Happy Path | P1 | [unsigned] |
| TC012 | Corner Case | P0 | [unsigned] |
| TC013 | Happy Path | P0 | [unsigned] |
| TC014 | Happy Path | P0 | [unsigned] |
| TC015 | Contract Check | P0 | [unsigned] |
| TC016 | Happy Path | P1 | [unsigned] |
| TC017 | Happy Path | P1 | [unsigned] |
| TC018 | Corner Case | P1 | [unsigned] |
| TC019 | Regression | P0 | [unsigned] |
| TC020 | Rollback Test | P0 | [unsigned] |

**Batch 1 progress: 0/20 signed**

---

## 🧪 BATCH 2 — Story A.2 First-Twin + A.8 First Briefing (TC021–TC040)

### TC021 — Twin auto-trigger sau khi nhập asset thật

**Story:** A.2 | **Type:** Happy Path | **Priority:** P0 | **Persona:** P1

**Setup:** User đã complete Step 1 (goal=understand_wealth), đang ở Step 2

**Steps:**
1. User gõ `300 triệu`
2. Bot acknowledge asset
3. Đợi 3-5s

**Expected:**
- `twin_engine_service.compute()` được gọi tự động (verify log)
- 3 message liên tiếp được push đến user (xem TC022-025)
- `onboarding_sessions.first_twin_shown_at` set = NOW()

**Signoff:** [unsigned]

---

### TC022 — Message 1: Mascot narrative trước cone chart

**Story:** A.2 | **Type:** Happy Path | **Priority:** P0 | **Persona:** P1

**Setup:** Đang ở post-asset step

**Steps:**
1. Sau khi nhập asset, quan sát message đầu tiên

**Expected:**
- Message text từ `first_twin_intro.yaml`
- Có substring: *"Đây là Twin tài chính của bạn"*
- Có substring 3 con đường: *"Đường giữa"*, *"Đường trên"*, *"Đường dưới"*
- Có closing: *"Bạn không cần đoán tương lai — Bé Tiền đoán giúp, bạn chỉ cần quyết định"*

**Signoff:** [unsigned]

---

### TC023 — Message 2: Cone chart image rendered

**Story:** A.2 | **Type:** Happy Path | **Priority:** P0 | **Persona:** P1

**Steps:**
1. Quan sát message thứ 2 sau narrative

**Expected:**
- Là image (PNG/JPG), không phải text
- Chart hiển thị cone với 3 đường (P10/P50/P90)
- Time horizon: ít nhất 12 tháng
- Background gradient, mascot góc dưới phải

**Signoff:** [unsigned]

---

### TC024 — Message 3: In-moment feedback prompt sau 5-10s delay

**Story:** A.2 | **Type:** Happy Path | **Priority:** P0 | **Persona:** P1

**Steps:**
1. Sau message cone chart, đếm giây
2. Quan sát message tiếp theo

**Expected:**
- Delay 7-10s (không immediate)
- Message: *"💬 Bạn cảm thấy thế nào về Twin đầu tiên?"*
- 3 inline button: 😍 / 🤔 / 😕

**Signoff:** [unsigned]

---

### TC025 — Bấm 😍 → save signal + acknowledge

**Story:** A.2 | **Type:** Happy Path | **Priority:** P0 | **Persona:** P1

**Steps:**
1. User bấm button 😍

**Expected:**
- `onboarding_sessions.onboarding_feedback_signal = '😍'`
- Row mới trong `feedbacks` với `onboarding_emoji_signal = '😍'`, status = 'open' (operator vẫn xem được trong inbox)
- Bot acknowledge: *"Cảm ơn bạn — Bé Tiền ghi nhận để cải thiện"*

**Signoff:** [unsigned]

---

### TC026 — Bấm 🤔 → save signal

**Story:** A.2 | **Type:** Happy Path | **Priority:** P1 | **Persona:** P5

**Steps:**
1. User bấm button 🤔

**Expected:**
- `onboarding_feedback_signal = '🤔'`
- Acknowledge giống TC025

**Signoff:** [unsigned]

---

### TC027 — Bấm 😕 → save signal (operator alert?)

**Story:** A.2 | **Type:** Corner Case | **Priority:** P0 | **Persona:** P5

**Steps:**
1. User bấm button 😕

**Expected:**
- `onboarding_feedback_signal = '😕'`
- Acknowledge ấm áp: *"Cảm ơn bạn nói thẳng — Bé Tiền sẽ học để làm tốt hơn"*
- Optional: tạo feedback record với priority='high' để operator review nhanh
- Nếu trong cohort có > 30% 😕 → kill criteria trigger (xem TC103)

**Signoff:** [unsigned]

---

### TC028 — TTFT < 5 phút từ `/start` đến cone chart

**Story:** A.2 | **Type:** Performance | **Priority:** P0 | **Persona:** P1

**Setup:** Clean staging account

**Steps:**
1. T0 = bấm `/start`
2. T1 = nhận cone chart image
3. Tính `T1 - T0`

**Expected:**
- `T1 - T0 < 5 minutes` (target), thực tế kỳ vọng < 90s
- Verify `onboarding_sessions.first_twin_shown_at - started_at < 300s`

**Signoff:** [unsigned]

---

### TC029 — Twin compute fail → fallback message

**Story:** A.2 | **Type:** Corner Case | **Priority:** P0 | **Persona:** P2

**Setup:** Mock `twin_engine_service.compute()` raise exception (vd: DeepSeek timeout)

**Steps:**
1. User nhập asset → trigger Twin
2. Quan sát phản hồi

**Expected:**
- KHÔNG để user ngồi nhìn `...` 30s
- Bot send fallback: *"Bé Tiền đang tính, bạn quay lại sau 1 phút nhé"*
- Sentry capture exception
- Worker retry sau 60s (nếu có retry logic) hoặc operator manual trigger

**Signoff:** [unsigned]

---

### TC030 — Resume worker: user stuck ở Step 2 > 10 phút → nhận 1 nudge

**Story:** A.2 | **Type:** Happy Path | **Priority:** P0 | **Persona:** P4

**Setup:**
- User vào Step 2, không nhập gì
- `onboarding_sessions.updated_at < NOW() - 10 minutes`
- `nudge_sent_at IS NULL`

**Steps:**
1. Đợi worker `onboarding_resume_worker` chạy (mỗi 5 phút)

**Expected:**
- Worker phát hiện row stuck
- Gửi 1 message: *"🌱 Bé Tiền đang chờ bạn ở bước [X] — chỉ cần thêm 1 thông tin là Twin sẵn sàng. Tiếp tục nhé?"*
- 2 inline button: "▶️ Tiếp tục" / "🤖 Để Bé Tiền dùng demo trước"
- `onboarding_sessions.nudge_sent_at = NOW()`

**Signoff:** [unsigned]

---

### TC031 — Resume nudge cap: KHÔNG gửi lần 2

**Story:** A.2 | **Type:** Corner Case | **Priority:** P0 | **Persona:** P4

**Setup:** User đã nhận nudge từ TC030, vẫn không hành động

**Steps:**
1. Đợi thêm 20 phút
2. Quan sát

**Expected:**
- Worker chạy nhưng KHÔNG gửi nudge thứ 2
- Query filter `nudge_sent_at IS NULL` → row này bị skip
- Không spam, không annoying

**Signoff:** [unsigned]

---

### TC032 — Bấm "Tiếp tục" trên resume nudge

**Story:** A.2 | **Type:** Happy Path | **Priority:** P1 | **Persona:** P4

**Steps:**
1. User bấm "▶️ Tiếp tục" trên nudge message

**Expected:**
- Bot phục hồi đúng Step user dừng (state machine reload)
- Prompt nguyên văn của step đó hiện lại
- `onboarding_sessions.updated_at = NOW()` (refresh)

**Signoff:** [unsigned]

---

### TC033 — Bấm "Để Bé Tiền dùng demo trước" trên resume nudge

**Story:** A.2 | **Type:** Happy Path | **Priority:** P1 | **Persona:** P4

**Steps:**
1. User bấm "🤖 Để Bé Tiền dùng demo trước"

**Expected:**
- Bot dẫn qua flow demo (giống TC013)
- Banner "Demo Mode" hiện rõ ràng

**Signoff:** [unsigned]

---

### TC034 — Onboarding completion log vào intent_logs

**Story:** A.2 | **Type:** Contract Check | **Priority:** P0 | **Persona:** P1

**Setup:** User hoàn tất onboarding

**Steps:**
1. Sau khi feedback emoji được bấm
2. Query `intent_logs`

**Expected:**
- Row mới với `action = ('onboarding', 'completed')`
- Metadata JSON chứa `goal` và `segment` (vd: `{"goal": "understand_wealth", "segment": "young_pro"}`)
- `onboarding_sessions.current_step = 'completed'`, `completed_at = NOW()`

**Signoff:** [unsigned]

---

### TC035 — A.8 First briefing detection: count=0 → áp first format

**Story:** A.8 | **Type:** Happy Path | **Priority:** P0 | **Persona:** P1

**Setup:**
- User completed onboarding hôm trước
- `briefing_logs` count cho user_id = 0

**Steps:**
1. 8h sáng ngày hôm sau, briefing worker chạy
2. Service `first_briefing_service` được gọi

**Expected:**
- Detect đây là first briefing (count = 0)
- Áp format đặc biệt (xem TC036)

**Signoff:** [unsigned]

---

### TC036 — First briefing format có explainer prefix

**Story:** A.8 | **Type:** Happy Path | **Priority:** P0 | **Persona:** P1

**Steps:**
1. User nhận first briefing 8h sáng

**Expected:**
- Message bắt đầu với: *"📍 Đây là briefing đầu tiên của bạn!"*
- Sau đó có giải thích cấu trúc: *"Mỗi sáng 8h Bé Tiền sẽ tổng hợp 3 thứ quan trọng nhất..."*
- Tiếp theo là 3 mục briefing (tổng tài sản, thay đổi, điều chú ý)
- Inline button "💡 Bé Tiền đang nói gì?"
- KHÔNG giống regular briefing (không có explainer prefix)

**Signoff:** [unsigned]

---

### TC037 — Bấm "Bé Tiền đang nói gì?" → hiện explanation

**Story:** A.8 | **Type:** Happy Path | **Priority:** P1 | **Persona:** P4

**Steps:**
1. Bấm inline button "💡 Bé Tiền đang nói gì?"

**Expected:**
- Bot send follow-up message giải thích 3 mục:
  - "Tổng tài sản" = ... (định nghĩa)
  - "Thay đổi vs hôm qua" = ... (định nghĩa)
  - "Điều Bé Tiền chú ý" = ... (định nghĩa)
- Content từ `first_briefing.yaml`

**Signoff:** [unsigned]

---

### TC038 — First briefing timing: 8h sáng ngày sau bất kể

**Story:** A.8 | **Type:** Happy Path | **Priority:** P0 | **Persona:** P2

**Setup:**
- User A onboard 11h sáng → expected first briefing: 8h ngày mai
- User B onboard 22h tối → expected first briefing: 8h ngày mai
- User C onboard 2h sáng → expected first briefing: 8h sáng cùng ngày? hay ngày mai?

**Steps:**
1. Tạo 3 user với onboarding_at khác nhau
2. Verify briefing schedule

**Expected:**
- Logic đơn giản: first briefing = 8h sáng **ngày dương lịch tiếp theo** sau onboarding (date+1)
- User A onboard 12/06 11h → first briefing 13/06 08:00
- User B onboard 12/06 22h → first briefing 13/06 08:00
- User C onboard 13/06 02:00 → first briefing 14/06 08:00 (NOT same day)
- KHÔNG có smart logic về user active

**Signoff:** [unsigned]

---

### TC039 — Second briefing dùng regular format (không phải first)

**Story:** A.8 | **Type:** Regression | **Priority:** P0 | **Persona:** P1

**Setup:** User đã nhận first briefing hôm qua

**Steps:**
1. 8h sáng ngày này, briefing worker chạy
2. Query `briefing_logs` count = 1

**Expected:**
- Service detect count >= 1 → áp regular format
- KHÔNG có explainer prefix
- KHÔNG có button "Bé Tiền đang nói gì?"
- Briefing y như Phase 4A/4B regular briefing

**Signoff:** [unsigned]

---

### TC040 — First briefing log event vào intent_logs

**Story:** A.8 | **Type:** Contract Check | **Priority:** P1 | **Persona:** P1

**Setup:** User nhận first briefing

**Steps:**
1. Query `intent_logs`

**Expected:**
- Row mới với `action = ('briefing', 'first_shown')`
- `user_id` đúng
- Timestamp khớp 8h sáng

**Signoff:** [unsigned]

---

## 📊 Batch 2 Summary

20 TCs (TC021-040): 12 Happy Path, 3 Corner Case, 2 Regression, 1 Performance, 2 Contract Check. All [unsigned].

---

## 🧪 BATCH 3 — Story A.3 Cost Guardrail + A.4 Daily Cost Report (TC041–TC060)

### TC041 — Mọi LLM call đi qua cost_tracking_adapter

**Story:** A.3 | **Type:** Contract Check | **Priority:** P0

**Setup:** Code review + integration test

**Steps:**
1. Trigger 1 intent classification (DeepSeek)
2. Trigger 1 OCR (Claude Vision)
3. Trigger 1 voice transcribe (Whisper)
4. Verify call stack

**Expected:**
- Tất cả 3 LLM call đi qua `cost_tracking_adapter` wrapper
- Direct call đến DeepSeek/Claude/Whisper adapter từ ngoài wrapper = FAIL contract check
- Grep code: không có `deepseek_adapter.call()` ngoài `cost_tracking_adapter`

**Signoff:** [unsigned]

---

### TC042 — Budget check trước call: trong limit → cho qua

**Story:** A.3 | **Type:** Happy Path | **Priority:** P0 | **Persona:** P1

**Setup:**
- User có `current_month_spend_vnd = 5000`, `monthly_cap_vnd = 30000` (free tier)

**Steps:**
1. Trigger 1 LLM call

**Expected:**
- Service check `5000 < 30000` → allow
- Call thành công, kết quả trả về
- `current_month_spend_vnd` tăng theo cost của call
- Row mới trong `llm_cost_log`

**Signoff:** [unsigned]

---

### TC043 — 80% threshold: gửi warning ấm áp 1 lần

**Story:** A.3 | **Type:** Happy Path | **Priority:** P0 | **Persona:** P2

**Setup:**
- User `current_month_spend_vnd = 24500`, `monthly_cap_vnd = 30000` (81.7%)
- `last_warning_sent_at = NULL`

**Steps:**
1. Trigger LLM call

**Expected:**
- Service detect 80%+ → gửi warning message từ `budget_messages.yaml`:
  - *"🌱 Bé Tiền note nhanh cho bạn..."* (xem deploy-announcements.md template)
- `last_warning_sent_at = NOW()`
- LLM call **vẫn được thực hiện** (warning, not block)
- Subsequent calls trong tháng KHÔNG gửi warning lại

**Signoff:** [unsigned]

---

### TC044 — 80% warning: không repeat trong cùng tháng

**Story:** A.3 | **Type:** Corner Case | **Priority:** P0 | **Persona:** P2

**Setup:** User đã nhận warning từ TC043, `last_warning_sent_at` trong tháng này

**Steps:**
1. Trigger 5 LLM call liên tiếp

**Expected:**
- Tất cả 5 call đều cho qua
- KHÔNG có warning message thứ 2
- User không bị spam

**Signoff:** [unsigned]

---

### TC045 — 100% threshold: BudgetExceededError raise

**Story:** A.3 | **Type:** Happy Path | **Priority:** P0 | **Persona:** P3

**Setup:** User `current_month_spend_vnd = 30000`, `monthly_cap_vnd = 30000` (100%)

**Steps:**
1. Trigger LLM call

**Expected:**
- Service raise `BudgetExceededError` ở layer service (không phải adapter)
- LLM provider KHÔNG được gọi (tiết kiệm cost thật)
- Exception caught bởi handler → trả user message

**Signoff:** [unsigned]

---

### TC046 — 100% block: user nhận warm message từ yaml

**Story:** A.3 | **Type:** Happy Path | **Priority:** P0 | **Persona:** P3

**Setup:** Continue TC045

**Steps:**
1. Quan sát message user nhận

**Expected:**
- Message từ `budget_messages.yaml`:
  - *"🌱 Bé Tiền tạm dừng tính năng [X] cho bạn tháng này — sang tháng mở lại nhé..."*
- Mention specific feature bị block (vd: "OCR hóa đơn")
- Suggest `/feedback` nếu cần gấp
- KHÔNG đổ lỗi user ("đây là hạn mức để Bé Tiền không 'đốt' tài nguyên — không phải bạn làm gì sai")

**Signoff:** [unsigned]

---

### TC047 — Default cap free = 30k

**Story:** A.3 | **Type:** Contract Check | **Priority:** P0

**Setup:** User mới onboard

**Steps:**
1. Query `user_cost_budgets` cho user mới

**Expected:**
- `tier = 'free'`
- `monthly_cap_vnd = 30000`
- `current_month_spend_vnd = 0`
- `current_month_started_at = today (first of month or onboard date)`

**Signoff:** [unsigned]

---

### TC048 — Default cap pro = 100k (test với manual tier change)

**Story:** A.3 | **Type:** Contract Check | **Priority:** P1

**Setup:**
- Manual SQL: `UPDATE user_cost_budgets SET tier='pro' WHERE user_id=...`
- Đồng thời update `monthly_cap_vnd = 100000`

**Steps:**
1. Verify cap

**Expected:**
- `tier = 'pro'`
- `monthly_cap_vnd = 100000`
- CHECK constraint `chk_tier_v1` allow 'pro'
- Note: trong Phase 4.1 tất cả user = free, đây là test để Phase 5.7 dùng

**Signoff:** [unsigned]

---

### TC049 — Mỗi LLM call success → log vào llm_cost_log

**Story:** A.3 | **Type:** Contract Check | **Priority:** P0

**Steps:**
1. Trigger 1 DeepSeek call
2. Query `llm_cost_log`

**Expected:**
- Row mới với:
  - `user_id` đúng
  - `provider = 'deepseek'`
  - `operation` (vd: `classify_intent`)
  - `tokens_in`, `tokens_out` đúng
  - `cost_vnd > 0`
  - `latency_ms > 0`
  - `created_at = NOW()`

**Signoff:** [unsigned]

---

### TC050 — CHECK constraint chk_tier_v1: cannot insert 'cfo'

**Story:** A.3 | **Type:** Security / Contract | **Priority:** P0

**Setup:** Migration `4.1.01` applied với CHECK constraint

**Steps:**
1. Try SQL: `UPDATE user_cost_budgets SET tier='cfo' WHERE user_id=...`

**Expected:**
- SQL FAIL với constraint violation error
- Verify constraint: `chk_tier_v1 CHECK (tier IN ('free', 'pro'))`
- Khi Phase 5.7 mở Max tier, sẽ DROP constraint trong migration mới

**Signoff:** [unsigned]

---

### TC051 — Operator command /budget_set override per-user

**Story:** A.3 | **Type:** Happy Path | **Priority:** P1

**Setup:** Operator command access (verify by OPERATOR_TELEGRAM_ID)

**Steps:**
1. Operator gõ `/budget_set <user_id> 50000`
2. Verify update

**Expected:**
- `user_cost_budgets.monthly_cap_vnd = 50000` cho user đó
- Operator nhận confirm: *"Budget cap cho user [id] = 50.000đ/tháng"*
- Non-operator user gõ command này → bị reject

**Signoff:** [unsigned]

---

### TC052 — cost_tracking_adapter KHÔNG gọi Telegram trực tiếp

**Story:** A.3 | **Type:** Contract Check | **Priority:** P0

**Setup:** Code review + `layer-contract-checker` agent

**Steps:**
1. Run layer-contract-checker on `adapters/llm/cost_tracking_adapter.py`

**Expected:**
- KHÔNG có import của Telegram bot library
- KHÔNG có call đến Notifier service
- Chỉ raise `BudgetExceededError` — service xử lý + return user message

**Signoff:** [unsigned]

---

### TC053 — cost_report_service.daily_summary trả đúng shape

**Story:** A.4 | **Type:** Contract Check | **Priority:** P0

**Steps:**
1. Call `cost_report_service.daily_summary(date='2026-06-15')`

**Expected:**
- Return object với fields:
  - `total_cost_vnd` (number)
  - `cost_by_provider` (dict: deepseek/claude/whisper)
  - `top_5_users` (list of {user_id_snippet, cost_vnd})
  - `users_at_80_pct` (list of user_id)
  - `is_anomaly` (boolean — true nếu > 200% avg 7d)

**Signoff:** [unsigned]

---

### TC054 — Top 5 user calculation đúng

**Story:** A.4 | **Type:** Happy Path | **Priority:** P0

**Setup:**
- Seed 10 user với cost khác nhau trong 24h: 5k, 4k, 3k, 2k, 1k, 800, 600, 400, 200, 100 đ

**Steps:**
1. Query daily_summary

**Expected:**
- `top_5_users` chứa 5 user với cost cao nhất: 5k, 4k, 3k, 2k, 1k
- Sắp xếp giảm dần
- User_id format snippet (8 chars đầu)

**Signoff:** [unsigned]

---

### TC055 — User mới chạm 80% trong ngày được liệt kê

**Story:** A.4 | **Type:** Happy Path | **Priority:** P1

**Setup:**
- User A chạm 80% hôm qua (đã warning)
- User B mới chạm 80% hôm nay

**Steps:**
1. Daily summary cho hôm nay

**Expected:**
- `users_at_80_pct` chỉ chứa User B (mới chạm trong 24h)
- User A KHÔNG xuất hiện (đã chạm hôm qua, đã warning rồi)
- Filter: `last_warning_sent_at` trong 24h

**Signoff:** [unsigned]

---

### TC056 — 🚨 flag khi total > 200% avg 7d

**Story:** A.4 | **Type:** Corner Case | **Priority:** P1

**Setup:**
- 7 ngày trước avg cost = 10k/ngày
- Hôm nay total = 25k (250%)

**Steps:**
1. Generate digest

**Expected:**
- Digest message bắt đầu với 🚨 emoji
- `is_anomaly = true`
- Operator nhận signal rõ ràng để check

**Signoff:** [unsigned]

---

### TC057 — Số liệu round về 1k VND

**Story:** A.4 | **Type:** Contract Check | **Priority:** P2

**Steps:**
1. Cost thực: 12.473đ
2. Format trong digest

**Expected:**
- Hiển thị `12.500đ` hoặc `~12k đ` (round to nearest 1000)
- Tất cả số trong digest đều round, không có decimal lẻ

**Signoff:** [unsigned]

---

### TC058 — Digest format < 500 chars cho cost section

**Story:** A.4 | **Type:** Contract Check | **Priority:** P2

**Steps:**
1. Generate cost section của KPI digest

**Expected:**
- Total characters của cost section < 500
- (Toàn bộ digest có thể > 500, nhưng cost section cần ngắn vì còn nhiều section khác)

**Signoff:** [unsigned]

---

### TC059 — Cost report MERGE vào KPI digest, không gửi standalone

**Story:** A.4 | **Type:** Contract Check | **Priority:** P0

**Steps:**
1. 8h sáng cron chạy
2. Đếm số message operator nhận

**Expected:**
- Chỉ 1 message duy nhất (KPI digest)
- KHÔNG có message riêng "Cost Report"
- Cost section nằm trong KPI digest message

**Signoff:** [unsigned]

---

### TC060 — Empty day handling: không có LLM call

**Story:** A.4 | **Type:** Corner Case | **Priority:** P1

**Setup:** 24h không có call nào (vd: bot mới deploy, chưa user)

**Steps:**
1. Generate daily summary

**Expected:**
- KHÔNG crash, KHÔNG NULL pointer
- Cost section: *"Total: 0đ — không có LLM call hôm nay"*
- Top 5 users: empty list, không hiển thị
- `is_anomaly = false`

**Signoff:** [unsigned]

---

## 📊 Batch 3 Summary

20 TCs (TC041-060): 8 Happy Path, 3 Corner Case, 9 Contract Check. All [unsigned].

---

## 🧪 BATCH 4 — Story A.5 Sentry + A.6 KPI Digest + A.7 Feedback Triage (TC061–TC080)

### TC061 — Sentry SDK wire vào FastAPI app

**Story:** A.5 | **Type:** Contract Check | **Priority:** P0

**Setup:** Bot deployed với `SENTRY_DSN` set

**Steps:**
1. Trigger 1 unhandled exception trong FastAPI handler (vd: divide by zero trong test endpoint)

**Expected:**
- Exception capture vào Sentry dashboard
- Stack trace đầy đủ
- Context có `user_id_hash` (không phải plain user_id)
- Sentry release version match với deployed version

**Signoff:** [unsigned]

---

### TC062 — Sentry SDK wire vào tất cả worker

**Story:** A.5 | **Type:** Contract Check | **Priority:** P0

**Setup:** Workers: `daily_kpi_digest_worker`, `cost_budget_worker`, `feedback_sla_worker`, `onboarding_resume_worker`, `twin_calibration_worker`

**Steps:**
1. Trigger exception trong mỗi worker
2. Verify Sentry capture cho từng worker

**Expected:**
- Tất cả 5 worker đều có Sentry init
- Capture đầy đủ context worker name + job name

**Signoff:** [unsigned]

---

### TC063 — PII scrub: tiền > 6 digit bị strip

**Story:** A.5 | **Type:** Security | **Priority:** P0

**Setup:** Trigger exception với message chứa `1500000000` (1.5 tỷ)

**Steps:**
1. Verify Sentry payload sau scrub

**Expected:**
- Số `1500000000` KHÔNG xuất hiện trong Sentry data
- Replaced với `[REDACTED_NUMBER]` hoặc tương tự
- Số nhỏ (<= 6 digit, vd: `100`, `12345`) vẫn pass — không over-scrub

**Signoff:** [unsigned]

---

### TC064 — PII scrub: email bị strip

**Story:** A.5 | **Type:** Security | **Priority:** P0

**Setup:** Exception message chứa `user@example.com`

**Steps:**
1. Verify Sentry payload

**Expected:**
- Email regex match → replaced với `[REDACTED_EMAIL]`
- Sentry KHÔNG lưu plain email

**Signoff:** [unsigned]

---

### TC065 — PII scrub: phone bị strip

**Story:** A.5 | **Type:** Security | **Priority:** P0

**Setup:** Exception message chứa `+84912345678` hoặc `0912345678`

**Steps:**
1. Verify Sentry payload

**Expected:**
- Phone regex match (cả format VN +84... và 0...) → replaced
- Sentry KHÔNG lưu plain phone

**Signoff:** [unsigned]

---

### TC066 — Whitelist approach, không phải blacklist

**Story:** A.5 | **Type:** Security / Contract Check | **Priority:** P0

**Steps:**
1. Trigger exception với 10 field random, một số chứa PII
2. Verify Sentry payload

**Expected:**
- Chỉ những field trong whitelist được pass: `intent_type`, `step`, `error_message_template_id`, `user_id_hash`
- Tất cả field khác bị strip mặc định (kể cả "harmless" field)
- KHÔNG dùng blacklist approach (dễ miss)

**Signoff:** [unsigned]

---

### TC067 — Metabase dashboard render đầy đủ 3 panel

**Story:** A.5 | **Type:** Happy Path | **Priority:** P1

**Setup:** Metabase connect PostgreSQL production, seed 1 tuần data

**Steps:**
1. Operator mở dashboard URL

**Expected:**
- Panel 1: Error rate per intent (last 24h + 7d)
- Panel 2: p50/p95 LLM latency per provider
- Panel 3: Daily active users (DAU trend)
- Tất cả load < 3s

**Signoff:** [unsigned]

---

### TC068 — KPI digest cron chạy đúng 8h ICT

**Story:** A.6 | **Type:** Happy Path | **Priority:** P0

**Setup:** Cron schedule đăng ký, timezone = `Asia/Ho_Chi_Minh`

**Steps:**
1. Đợi 8h sáng (hoặc trigger manual)
2. Verify operator nhận message

**Expected:**
- Message arrive lúc 8:00:00–8:00:59 ICT
- Đúng `OPERATOR_TELEGRAM_ID` từ ENV
- Nếu cron fail (vd: DB down) → Sentry alert

**Signoff:** [unsigned]

---

### TC069 — Single message chứa đủ 5 section

**Story:** A.6 | **Type:** Contract Check | **Priority:** P0

**Steps:**
1. Verify digest content structure

**Expected:**
- 5 section rõ ràng: 💸 Cost, 📊 Engagement, 🎯 Quality, ⚠️ Churn signals, 📝 Feedback queue
- Section divider rõ ràng (emoji + heading)
- Total length < 4000 chars (Telegram limit)

**Signoff:** [unsigned]

---

### TC070 — DAU/WAU/MAU calculation đúng

**Story:** A.6 | **Type:** Happy Path | **Priority:** P0

**Setup:** Seed `intent_logs` với 30 ngày data

**Steps:**
1. Generate KPI digest
2. Verify DAU/WAU/MAU số

**Expected:**
- DAU = distinct user_id có `intent_logs` trong 24h
- WAU = distinct user_id có `intent_logs` trong 7d
- MAU = distinct user_id có `intent_logs` trong 30d
- Match với SQL manual query

**Signoff:** [unsigned]

---

### TC071 — Intent classification accuracy %

**Story:** A.6 | **Type:** Contract Check | **Priority:** P1

**Setup:** 100 intent calls với mix outcome

**Steps:**
1. Calculate accuracy

**Expected:**
- Formula: `confirmed_count / (confirmed + clarified + misexecuted)`
- Hiển thị `% với breakdown numbers`: vd *"87% (12 confirmed, 2 clarified, 0 misexecuted của 14 calls)"*

**Signoff:** [unsigned]

---

### TC072 — In-onboarding emoji distribution

**Story:** A.6 | **Type:** Happy Path | **Priority:** P0

**Setup:** 10 user complete onboarding với mix emoji: 6 😍, 3 🤔, 1 😕

**Steps:**
1. KPI digest 24h

**Expected:**
- Section Quality hiển thị: `😍 6 | 🤔 3 | 😕 1`
- Hoặc percentage: `😍 60% | 🤔 30% | 😕 10%`

**Signoff:** [unsigned]

---

### TC073 — Churn signals list user inactive 7+ ngày

**Story:** A.6 | **Type:** Happy Path | **Priority:** P1

**Setup:**
- User A active hôm qua → KHÔNG churn
- User B last seen 8 ngày trước → churn signal
- User B là founding member #12

**Steps:**
1. KPI digest

**Expected:**
- Section Churn liệt kê User B với:
  - `user_id_snippet`
  - `founding flag (#12)` nếu có
  - `last_seen = 8 days ago`

**Signoff:** [unsigned]

---

### TC074 — Standalone script kpi_digest.py chạy được

**Story:** A.6 | **Type:** Happy Path | **Priority:** P1

**Steps:**
1. Operator chạy `python scripts/kpi_digest.py --date 2026-06-15`

**Expected:**
- Output ra stdout/file dạng giống message Telegram
- KHÔNG gửi qua Telegram (script mode)
- Useful cho backfill hoặc ad-hoc report

**Signoff:** [unsigned]

---

### TC075 — /feedback_inbox liệt kê đúng feedback open

**Story:** A.7 | **Type:** Happy Path | **Priority:** P0

**Setup:** Seed 5 feedback với status mix: 3 open, 2 answered

**Steps:**
1. Operator gõ `/feedback_inbox`

**Expected:**
- Bot trả về list 3 feedback (status='open')
- Sort theo `created_at` cũ nhất trước
- Mỗi feedback hiển thị: ID 8 chars, wealth_segment, snippet 100 chars, age
- 2 feedback `answered` KHÔNG xuất hiện

**Signoff:** [unsigned]

---

### TC076 — Feedback từ founding member có flag 🌱

**Story:** A.7 | **Type:** Happy Path | **Priority:** P1

**Setup:** 1 feedback từ founding member, 1 từ non-founding

**Steps:**
1. `/feedback_inbox`

**Expected:**
- Feedback founding hiển thị icon 🌱 trong dòng
- Non-founding không có icon
- Operator dễ nhìn để prioritize founding feedback

**Signoff:** [unsigned]

---

### TC077 — /feedback_reply gửi message cho user + update status

**Story:** A.7 | **Type:** Happy Path | **Priority:** P0

**Steps:**
1. Operator gõ `/feedback_reply abc12345 Cảm ơn bạn đã góp ý`
2. Verify

**Expected:**
- User nhận message: *"Cảm ơn bạn đã góp ý"* từ Bé Tiền
- `feedbacks.first_responded_at = NOW()`
- `feedbacks.status = 'answered'`
- Bot confirm operator: *"Đã reply feedback abc12345"*

**Signoff:** [unsigned]

---

### TC078 — Template thanks_logged render đúng

**Story:** A.7 | **Type:** Happy Path | **Priority:** P1

**Steps:**
1. Operator gõ `/feedback_reply abc12345 --template thanks_logged`

**Expected:**
- User nhận content từ `triage_responses.yaml.thanks_logged`:
  - *"Cảm ơn bạn — Bé Tiền đã ghi nhận và đang xem qua."*
- 5 templates available: `thanks_logged`, `clarify_request`, `feature_acknowledged`, `bug_apology`, `not_supported_yet`

**Signoff:** [unsigned]

---

### TC079 — SLA worker alert sau 24h

**Story:** A.7 | **Type:** Happy Path | **Priority:** P0

**Setup:**
- 1 feedback `status='open'`, `created_at = NOW() - 25 hours`
- `sla_breach_alerted_at = NULL`

**Steps:**
1. Đợi `feedback_sla_worker` chạy (mỗi giờ)

**Expected:**
- Worker phát hiện row > 24h
- Gửi alert đến operator: *"⏰ Feedback abc12345 đã quá 24h chưa trả lời..."*
- `sla_breach_alerted_at = NOW()`

**Signoff:** [unsigned]

---

### TC080 — SLA worker không repeat alert per feedback

**Story:** A.7 | **Type:** Corner Case | **Priority:** P0

**Setup:** Feedback từ TC079 đã có `sla_breach_alerted_at` set, vẫn `status='open'`

**Steps:**
1. Đợi worker chạy thêm 3 lần

**Expected:**
- KHÔNG có alert thứ 2 cho cùng feedback
- Filter `sla_breach_alerted_at IS NULL` → row này bị skip
- Operator không bị spam

**Signoff:** [unsigned]

---

## 📊 Batch 4 Summary

20 TCs (TC061-080): 9 Happy Path, 1 Corner Case, 4 Security, 6 Contract Check. All [unsigned].

---

## 🧪 BATCH 5 — Story B.1 Share Image + B.2 Calibration + C.1 Invite + C.4 Founding (TC081–TC100)

### TC081 — Nút "📸 Lưu thành ảnh" xuất hiện trong Twin view

**Story:** B.1 | **Type:** Happy Path | **Priority:** P1 | **Persona:** P2

**Setup:** User đã có Twin (sau onboarding)

**Steps:**
1. User mở Twin view (qua menu hoặc command)

**Expected:**
- Twin view có inline button "📸 Lưu thành ảnh" cuối message
- Bấm vào → trigger render

**Signoff:** [unsigned]

---

### TC082 — PNG rendered KHÔNG chứa số tiền tuyệt đối

**Story:** B.1 | **Type:** Security | **Priority:** P0 | **Persona:** P2

**Setup:** User wealth = 1.5 tỷ

**Steps:**
1. Bấm "📸 Lưu thành ảnh"
2. Inspect PNG output

**Expected:**
- Image KHÔNG có số `1.500.000.000` hoặc `1.5 tỷ` hiển thị
- Chỉ có: % tăng trưởng (vd: "+45% trong 5 năm"), time horizon
- Watermark "Bé Tiền — Personal CFO" góc dưới

**Signoff:** [unsigned]

---

### TC083 — Mascot + gradient background

**Story:** B.1 | **Type:** Happy Path | **Priority:** P2

**Steps:**
1. Render image
2. Visual check

**Expected:**
- Background có gradient (không phải solid color)
- Mascot Bé Tiền góc dưới phải, kích thước phù hợp (không che chart)
- Chart cone hiển thị rõ ràng

**Signoff:** [unsigned]

---

### TC084 — Founding badge xuất hiện nếu is_founding_member=TRUE

**Story:** B.1 | **Type:** Happy Path | **Priority:** P1

**Setup:**
- User A: `is_founding_member=TRUE`
- User B: `is_founding_member=FALSE`

**Steps:**
1. Cả 2 user bấm "📸 Lưu thành ảnh"

**Expected:**
- Image của User A: có badge "🌱 Founding Member" góc trên trái
- Image của User B: KHÔNG có badge

**Signoff:** [unsigned]

---

### TC085 — Render time < 1s

**Story:** B.1 | **Type:** Performance | **Priority:** P1

**Steps:**
1. Đo time từ button press đến image delivered
2. Repeat 10 lần

**Expected:**
- p50 < 1s
- p95 < 2s
- Nếu p95 > 2s → kill feature theo recommendation #4 trong detailed.md

**Signoff:** [unsigned]

---

### TC086 — Snapshot log mỗi lần Twin opened

**Story:** B.2 | **Type:** Happy Path | **Priority:** P0

**Steps:**
1. User mở Twin view
2. Query `twin_calibration_snapshots`

**Expected:**
- 3 row mới được tạo cùng lúc (1 cho mỗi horizon):
  - `horizon_days = 7`
  - `horizon_days = 30`
  - `horizon_days = 90`
- Tất cả có `predicted_at = NOW()`, `actual_vnd = NULL`, `within_band = NULL`
- `p10_vnd`, `p50_vnd`, `p90_vnd` đúng từ Twin computation

**Signoff:** [unsigned]

---

### TC087 — Worker fill actual_vnd khi horizon hits

**Story:** B.2 | **Type:** Happy Path | **Priority:** P0

**Setup:** Snapshot có `predicted_at = NOW() - 7 days`, `horizon_days = 7`, `actual_vnd = NULL`

**Steps:**
1. `twin_calibration_worker` chạy daily

**Expected:**
- Worker phát hiện row due (`predicted_at + horizon_days <= NOW()`)
- Fill `actual_vnd` từ current net worth của user
- Set `actual_recorded_at = NOW()`
- Compute `within_band = (p10 <= actual <= p90)`

**Signoff:** [unsigned]

---

### TC088 — within_band calculation correct

**Story:** B.2 | **Type:** Contract Check | **Priority:** P0

**Setup:**
- Snapshot 1: p10=100, p50=150, p90=200, actual=180 → within_band=TRUE
- Snapshot 2: p10=100, p50=150, p90=200, actual=250 → within_band=FALSE
- Snapshot 3: p10=100, p50=150, p90=200, actual=50 → within_band=FALSE

**Steps:**
1. Worker process all

**Expected:**
- Snapshot 1: within_band=TRUE
- Snapshot 2: within_band=FALSE (actual > p90)
- Snapshot 3: within_band=FALSE (actual < p10)
- Edge: actual == p10 hoặc == p90 → within_band=TRUE (inclusive)

**Signoff:** [unsigned]

---

### TC089 — Section "🎯 Bé Tiền đoán đúng?" chỉ hiện khi ≥ 3 snapshot completed

**Story:** B.2 | **Type:** Corner Case | **Priority:** P0

**Setup:**
- User A: 2 completed snapshot → KHÔNG hiện section
- User B: 3 completed snapshot → hiện section
- User C: 9 completed (7 within, 2 outside) → hiện 78%

**Steps:**
1. Mỗi user mở Twin view

**Expected:**
- User A: section vắng mặt
- User B: hiện *"Bé Tiền đoán đúng X/3 lần (Y%)"*
- User C: hiện *"Bé Tiền đoán đúng 7/9 lần (78%)"*

**Signoff:** [unsigned]

---

### TC090 — Hit rate < 50% → disclaimer "đang học thêm"

**Story:** B.2 | **Type:** Corner Case | **Priority:** P1

**Setup:** User có 10 completed snapshot, chỉ 3 within_band (30%)

**Steps:**
1. User mở Twin view

**Expected:**
- Section hiển thị: *"Bé Tiền đoán đúng 3/10 lần (30%)"*
- Thêm disclaimer: *"Dự phóng chưa chuẩn, Bé Tiền đang học thêm — bạn vẫn tham khảo trend chung được"*
- KHÔNG hide số (honest framing)
- KHÔNG inflate

**Signoff:** [unsigned]

---

### TC091 — Backfill script chạy được trên data Phase 4A

**Story:** B.2 | **Type:** Happy Path | **Priority:** P2

**Steps:**
1. Chạy `python scripts/twin_calibration_backfill.py --start-date 2026-04-01`

**Expected:**
- Script replay past Twin runs từ Phase 4A
- Insert vào `twin_calibration_snapshots` với `predicted_at` đúng thời điểm gốc
- Idempotent: chạy 2 lần KHÔNG tạo duplicate

**Signoff:** [unsigned]

---

### TC092 — Script generate exactly 50 invite

**Story:** C.1 | **Type:** Happy Path | **Priority:** P0

**Steps:**
1. Chạy `python scripts/soft_launch_acquisition.py`

**Expected:**
- Exactly 50 row mới trong `invite_codes`
- Mỗi row unique `token`
- Tất cả có `grants_founding_status=TRUE`
- Source distribution match plan: 12 friends, 8 personal_fb, 15 vn_finance_community, 10 tg_finance_groups, 5 direct_msg

**Signoff:** [unsigned]

---

### TC093 — Tất cả invite có grants_founding_status=TRUE

**Story:** C.1 + C.4 | **Type:** Contract Check | **Priority:** P0

**Steps:**
1. Query: `SELECT count(*) FROM invite_codes WHERE grants_founding_status=FALSE AND batch_name='soft_launch_2026_06'`

**Expected:**
- Count = 0
- Tất cả 50 invite của batch này grants founding status

**Signoff:** [unsigned]

---

### TC094 — /cohort_stats breakdown theo source

**Story:** C.1 | **Type:** Happy Path | **Priority:** P1

**Setup:** 10 user đã redeem từ các source khác nhau

**Steps:**
1. Operator gõ `/cohort_stats`

**Expected:**
- Output dạng:
  - `friends: 3 users (60% completed onboarding)`
  - `vn_finance_community: 4 users (75%)`
  - `tg_finance_groups: 2 users (50%)`
  - `direct_msg: 1 user (100%)`
  - `personal_fb: 0 users`
- Total: 10/50 redeemed

**Signoff:** [unsigned]

---

### TC095 — CSV output 50 dòng đầy đủ

**Story:** C.1 | **Type:** Happy Path | **Priority:** P1

**Steps:**
1. Script generate xong → output CSV

**Expected:**
- File CSV 50 dòng + 1 header row
- Columns: `invite_url`, `source`, `batch_name`, `token`
- Sorted hoặc grouped theo source
- Encoding UTF-8

**Signoff:** [unsigned]

---

### TC096 — Founding sequence atomic: 5 user redeem cùng giây

**Story:** C.4 | **Type:** Security / Concurrency | **Priority:** P0

**Setup:** 5 invite code chưa redeem

**Steps:**
1. Trigger 5 user redeem song song (qua script test concurrent)
2. Query sequences

**Expected:**
- 5 user nhận sequence 1, 2, 3, 4, 5 (no duplicate, no gap)
- Implementation dùng `SELECT ... FOR UPDATE` hoặc PostgreSQL advisory lock
- Verify constraint UNIQUE trên `founding_member_sequence`

**Signoff:** [unsigned]

---

### TC097 — Founding banner trong welcome message

**Story:** C.4 | **Type:** Happy Path | **Priority:** P0

**Setup:** User redeem invite với `grants_founding_status=TRUE`, sequence = #15

**Steps:**
1. Quan sát welcome message

**Expected:**
- Banner xuất hiện:
  - *"🌱 Bạn là Founding Member #15 của Bé Tiền — 1 trong 50 người đầu tiên..."*
  - *"...giảm 50% trọn đời — 44.000đ/tháng thay vì 88.000đ..."*
- Banner stand-out, không lẫn vào generic copy

**Signoff:** [unsigned]

---

### TC098 — /whoami hiển thị founding sequence

**Story:** C.4 | **Type:** Happy Path | **Priority:** P1

**Setup:** User founding #15

**Steps:**
1. User gõ `/whoami`

**Expected:**
- Output:
  - `wealth_segment: young_pro` (hoặc segment đúng)
  - `onboarding_date: DD/MM/YYYY`
  - `🌱 Founding Member #15`
  - `days_active: N`
- Non-founding user: không có dòng Founding Member

**Signoff:** [unsigned]

---

### TC099 — /founding_status liệt kê tất cả 50

**Story:** C.4 | **Type:** Happy Path | **Priority:** P1

**Setup:** 50 founding member đã onboard

**Steps:**
1. Operator gõ `/founding_status`

**Expected:**
- Output table với 50 dòng (hoặc paginate nếu Telegram limit):
  - sequence | onboarding_date | days_active | last_seen
- Sorted theo sequence ASC
- Highlight user inactive 7+ ngày (vd: ⚠️ emoji)

**Signoff:** [unsigned]

---

### TC100 — compute_discount() returns 0.5 cho founding

**Story:** C.4 | **Type:** Contract Check | **Priority:** P0

**Setup:**
- User A: founding
- User B: not founding

**Steps:**
1. Call `founding_member_service.compute_discount(user_A.id)` → expect `0.5`
2. Call `founding_member_service.compute_discount(user_B.id)` → expect `0`

**Expected:**
- Function ready cho Phase 5.7 dùng
- Test unit test pass
- Documented trong `founding-promise.md`

**Signoff:** [unsigned]

---

## 📊 Batch 5 Summary

20 TCs (TC081-100): 12 Happy Path, 2 Corner Case, 2 Security, 4 Contract Check. All [unsigned].

---

## 🧪 BATCH 6 — Cross-Cutting Tests (TC101–TC120)

### TC101 — Regression: Phase 4A Twin computation vẫn hoạt động

**Story:** Cross | **Type:** Regression | **Priority:** P0 | **Persona:** P2

**Setup:** User cũ (`created_at < phase_4_1_deploy_date`) đã có Twin từ Phase 4A

**Steps:**
1. User cũ mở Twin view
2. Verify

**Expected:**
- Twin compute thành công, không error
- Cone chart render đúng dữ liệu của user (không bị mất sau migration)
- Phase 4B life event simulator vẫn hoạt động
- KHÔNG có data loss

**Signoff:** [unsigned]

---

### TC102 — Regression: Phase 4B life event simulator vẫn work

**Story:** Cross | **Type:** Regression | **Priority:** P0 | **Persona:** P2

**Steps:**
1. User mở life event simulator (existing Phase 4B feature)
2. Add scenario "Mua nhà 3 tỷ trong 5 năm"
3. Verify output

**Expected:**
- Simulator chạy bình thường
- Output Twin cone phản ánh scenario
- KHÔNG bị Phase 4.1 break

**Signoff:** [unsigned]

---

### TC103 — Regression: Existing /help command

**Story:** Cross | **Type:** Regression | **Priority:** P1

**Steps:**
1. User gõ `/help`

**Expected:**
- Bot trả về help message từ Phase 3A/4A (không bị Phase 4.1 override)
- Có thể đã update để mention features mới (Twin, founding), nhưng base structure giữ

**Signoff:** [unsigned]

---

### TC104 — Regression: Existing intent classification (5 sample queries)

**Story:** Cross | **Type:** Regression | **Priority:** P0

**Setup:** 5 sample query đã test trước Phase 4.1

**Steps:**
1. Gửi từng query, verify classification

**Expected:**
- 5/5 classify đúng intent như trước (vd: "tài sản của tôi" → `query_total_wealth`)
- Latency không tệ hơn (vì có thêm cost_tracking_adapter wrap)
- Cost log đầy đủ (mới có)

**Signoff:** [unsigned]

---

### TC105 — Regression: ZALO_CHANNEL_ENABLED=false → Zalo handler không active

**Story:** Cross | **Type:** Regression / Security | **Priority:** P0

**Setup:**
- ENV `ZALO_CHANNEL_ENABLED=false`
- Phase 4B Zalo OA adapter có trong codebase

**Steps:**
1. Grep code: tất cả Zalo router/handler registration phải gate qua flag
2. Deploy lên staging với flag=false
3. Try gọi Zalo OA endpoint giả

**Expected:**
- Zalo router KHÔNG đăng ký vào FastAPI
- Endpoint trả 404 hoặc 503
- Sentry KHÔNG có error noise từ Zalo
- Verify env config 2 lần trước launch (checklist trong deploy doc)

**Signoff:** [unsigned]

---

### TC106 — Security: SQL injection trong goal_choice

**Story:** Cross | **Type:** Security | **Priority:** P0

**Setup:** User gửi malformed callback data với SQL payload (vd: `'; DROP TABLE users; --`)

**Steps:**
1. Send malicious callback to bot
2. Verify

**Expected:**
- Service reject input, không execute SQL
- ORM (SQLAlchemy) parameterized query → injection failed
- Log warning event vào Sentry
- User không thấy lỗi (graceful fallback)

**Signoff:** [unsigned]

---

### TC107 — Security: PII scrub Sentry với real exception

**Story:** Cross | **Type:** Security | **Priority:** P0

**Setup:** Mock real exception trong production-like setting

**Steps:**
1. Trigger exception với context chứa user message có tiền + email + phone
2. Verify Sentry payload

**Expected:**
- 0/3 PII fields visible trong Sentry
- Stack trace vẫn đầy đủ → debuggable
- Operator có thể đọc Sentry mà không sợ leak PII của user

**Signoff:** [unsigned]

---

### TC108 — Security: Founding sequence race condition stress test

**Story:** Cross | **Type:** Security / Concurrency | **Priority:** P0

**Setup:** Stress test với 50 concurrent redeem

**Steps:**
1. Tạo 50 invite, trigger 50 user redeem cùng lúc qua script
2. Query sequences

**Expected:**
- 50 sequences từ 1 đến 50, no duplicate, no gap, no skip
- KHÔNG có row với `is_founding_member=TRUE` và `founding_member_sequence=NULL`
- Test này quan trọng vì soft launch sẽ có spike khi operator gửi invite cùng lúc

**Signoff:** [unsigned]

---

### TC109 — Security: Invite token không reuse được

**Story:** Cross | **Type:** Security | **Priority:** P0

**Setup:** Invite token A đã redeem bởi User 1

**Steps:**
1. User 2 thử dùng cùng token A
2. Verify

**Expected:**
- User 2 nhận message expired/used (như TC003)
- User 2 KHÔNG được founding status
- Token có status flag `redeemed_at IS NOT NULL`

**Signoff:** [unsigned]

---

### TC110 — Security: Budget cap không bypass được qua direct SQL

**Story:** Cross | **Type:** Security | **Priority:** P0

**Setup:**
- Try SQL trực tiếp: `UPDATE user_cost_budgets SET monthly_cap_vnd = 999999999 WHERE user_id=...`
- (Đây là test rằng adapter code không có path bypass — không phải test rằng DB không bypass được)

**Steps:**
1. Code review: tất cả LLM call path đều check cap
2. Try gọi `deepseek_adapter.call()` trực tiếp (bypass cost_tracking_adapter)

**Expected:**
- Direct call FAIL contract check (vi phạm wrapper rule)
- `layer-contract-checker` agent catch được
- KHÔNG có code path nào skip cost check

**Signoff:** [unsigned]

---

### TC111 — Performance: TTFT under load (10 concurrent onboarding)

**Story:** Cross | **Type:** Performance | **Priority:** P1

**Setup:** Staging với 10 fake user trigger /start cùng lúc

**Steps:**
1. Đo TTFT cho mỗi user
2. p50, p95, p99

**Expected:**
- p50 < 90s
- p95 < 180s (3 phút)
- p99 < 300s (5 phút — boundary)
- KHÔNG có user nào fail (timeout, error)

**Signoff:** [unsigned]

---

### TC112 — Performance: KPI digest compute < 30s

**Story:** Cross | **Type:** Performance | **Priority:** P1

**Setup:** Production-like data: 50 users, 7 days history

**Steps:**
1. Time `python scripts/kpi_digest.py`

**Expected:**
- Total time < 30s
- Nếu > 30s → optimize SQL queries (add indexes if needed)

**Signoff:** [unsigned]

---

### TC113 — Performance: Twin image render p95 < 1s

**Story:** Cross / B.1 | **Type:** Performance | **Priority:** P1

**Steps:**
1. Render 100 images với data ngẫu nhiên
2. p95 measurement

**Expected:**
- p95 < 1s (target)
- p99 < 2s
- Memory không leak qua 100 lần render

**Signoff:** [unsigned]

---

### TC114 — Performance: Cost guardrail middleware overhead

**Story:** Cross / A.3 | **Type:** Performance | **Priority:** P1

**Setup:** Compare LLM call latency với + không có middleware

**Steps:**
1. Direct call DeepSeek (bypass) — measure latency
2. Through cost_tracking_adapter — measure latency
3. Diff

**Expected:**
- Overhead < 50ms per call (1 DB read + 1 DB write for log)
- Total latency tăng < 5%

**Signoff:** [unsigned]

---

### TC115 — Persona: P5 Anh Khải (skeptical) complete onboarding

**Story:** Cross | **Type:** Persona E2E | **Priority:** P1 | **Persona:** P5

**Setup:** Operator role-play như P5 — skeptical, low-trust, mass affluent

**Steps:**
1. Run full E2E onboarding như P5 sẽ làm:
   - Start với invite từ vn_finance_community
   - Step 1: chọn "Hiểu rõ tổng tài sản" (skeptical user thường muốn thấy data trước)
   - Step 2: dùng demo trước (không nhập số thật vì skeptical)
   - Xem Twin demo
   - Quay lại nhập số thật (3.2 tỷ)
   - Xem Twin thật
   - Bấm 🤔 (skeptical neutral signal)

**Expected:**
- Flow chạy mượt, không glitch
- Demo mode framing đủ rõ để skeptical user trust
- Twin output đủ thuyết phục (% trong band) để 🤔 không thành 😕
- Mascot narrative chạm tone đúng (không sales-y)

**Signoff:** [unsigned]

---

### TC116 — Persona: P3 Chị Hương (low-tech) complete onboarding

**Story:** Cross | **Type:** Persona E2E | **Priority:** P1 | **Persona:** P3

**Setup:** Operator role-play như P3 — low-tech, mass affluent businesswoman, ít dùng Telegram

**Steps:**
1. Run E2E với pace chậm hơn (delay 30-60s giữa các action)
2. Resume nudge có thể trigger (test cả nudge flow)

**Expected:**
- Resume nudge KHÔNG annoying — chỉ 1 lần
- Copy đơn giản, không dùng từ technical
- User cuối cùng vẫn complete được Twin
- Emoji feedback: 😍 hoặc 🤔

**Signoff:** [unsigned]

---

### TC117 — Persona compliance: Bé Tiền voice check

**Story:** Cross | **Type:** Persona | **Priority:** P0

**Setup:** Manual review toàn bộ user-facing copy (all yaml files)

**Steps:**
1. Grep cấm từ: "khách hàng", "siêu", "tốt nhất", "đẳng cấp", "hoàn hảo"
2. Grep require: 🌱 emoji (Bé Tiền signature), "bạn" (không phải "khách hàng")
3. Review tone: không sales-y, không hype

**Expected:**
- 0 occurrence của cấm từ
- 🌱 emoji có trong key touchpoint (welcome, founding banner, briefing)
- Tone consistent: ấm áp, không formal-business, không hype
- Vietnamese strings có dấu đầy đủ

**Signoff:** [unsigned]

---

### TC118 — Contract: layer-contract-checker — không db.commit trong service

**Story:** Cross | **Type:** Contract Check | **Priority:** P0

**Steps:**
1. Run `layer-contract-checker` agent trên `services/*`

**Expected:**
- Agent pass: KHÔNG có `db.commit()` trong bất kỳ service nào
- Tất cả services chỉ `db.flush()`
- Commit chỉ ở worker boundary hoặc handler

**Signoff:** [unsigned]

---

### TC119 — Contract: layer-contract-checker — không business logic trong adapter

**Story:** Cross | **Type:** Contract Check | **Priority:** P0

**Steps:**
1. Run agent trên `adapters/*`

**Expected:**
- KHÔNG có if-else business logic trong adapter
- Adapter chỉ wrap external library/API call
- `cost_tracking_adapter` raise exception, không decide gì
- Domain decisions ở service layer

**Signoff:** [unsigned]

---

### TC120 — Contract: vi-localization-checker — full code base pass

**Story:** Cross | **Type:** Contract Check | **Priority:** P0

**Steps:**
1. Run `vi-localization-checker` agent trên toàn bộ `bot/`, `services/`, `workers/`, `adapters/`

**Expected:**
- KHÔNG có hardcoded Vietnamese string trong .py file
- Tất cả copy nằm trong `content/*.yaml`
- Error messages template-based (vd: `template_id="budget_exceeded"`)
- Sign-off marker `signed` cho merge

**Signoff:** [unsigned]

---

## 📊 Batch 6 Summary

20 TCs (TC101-120): 5 Regression, 5 Security, 4 Performance, 3 Persona, 3 Contract Check. All [unsigned].

---

## ✅ Final Test Plan Summary

| Batch | TC Range | Stories Covered | Count | Signed |
|---|---|---|---|---|
| 1 | TC001-020 | A.1 Onboarding redesign | 20 | 0 |
| 2 | TC021-040 | A.2 First-Twin + A.8 First briefing | 20 | 0 |
| 3 | TC041-060 | A.3 Cost guardrail + A.4 Daily cost report | 20 | 0 |
| 4 | TC061-080 | A.5 Sentry + A.6 KPI digest + A.7 Feedback triage | 20 | 0 |
| 5 | TC081-100 | B.1 Share image + B.2 Calibration + C.1 Invite + C.4 Founding | 20 | 0 |
| 6 | TC101-120 | Cross-cutting (regression/security/performance/persona/contract) | 20 | 0 |
| **Total** | **120 TCs** | **All 13 stories + cross-cutting** | **120** | **0** |

### Distribution by Type

| Type | Count | % |
|---|---|---|
| Happy Path | 54 | 45% |
| Corner Case | 9 | 8% |
| Regression | 7 | 6% |
| Security | 13 | 11% |
| Performance | 5 | 4% |
| Persona | 5 | 4% |
| Contract Check | 26 | 22% |
| Rollback Test | 1 | 1% |
| **Total** | **120** | **100%** |

### Distribution by Priority

| Priority | Count | % |
|---|---|---|
| P0 (must pass) | ~75 | ~62% |
| P1 (should pass) | ~40 | ~33% |
| P2 (nice to have) | ~5 | ~5% |

### Test Execution Strategy

**Phase 1 — Smoke test (1 ngày):**
- All P0 Happy Path TCs (~30 TCs)
- All Contract Check TCs (~26 TCs)
- Target: ≥ 95% pass

**Phase 2 — Full pass (2-3 ngày):**
- Remaining P0 + all P1 (~80 TCs)
- All Persona E2E (5 TCs)
- Target: ≥ 90% pass

**Phase 3 — Edge & stress (1 ngày):**
- Corner Case + Security + Performance + Concurrency (~30 TCs)
- Target: 100% P0 pass; P1 fail acceptable nếu non-blocking

**Phase 4 — Sign-off (0.5 ngày):**
- Re-run failed TCs sau fix
- Sign all `[unsigned]` → `[signed: name-2026-MM-DD]`
- Final sign-off marker trong commit message

### Definition of "Test Plan Done"

- [ ] 100% P0 TCs `[signed]`
- [ ] ≥ 90% P1 TCs `[signed]`
- [ ] All 5 persona E2E walkthrough completed
- [ ] All cross-cutting contract checks pass
- [ ] 0 unresolved security TCs
- [ ] Performance benchmarks documented (TTFT p50/p95/p99, render time, digest time)
- [ ] Sign-off block added to `phase-4.1-deploy-announcements.md` checklist

---

## 🚨 Critical Path TCs (must pass before soft launch)

These are gating — if any FAIL, soft launch BLOCKED:

| TC | Story | Reason |
|---|---|---|
| TC001 | A.1 | First touchpoint cho user — must work |
| TC008 | A.1 | Wealth inference từ asset đầu — affects segmentation |
| TC021 | A.2 | Twin auto-trigger — core wow moment |
| TC028 | A.2 | TTFT < 5 phút — promise metric |
| TC035-036 | A.8 | First briefing — first impression Day 2 |
| TC041 | A.3 | Cost adapter wrap all — financial safety |
| TC045-046 | A.3 | 100% block message — financial safety |
| TC068 | A.6 | KPI digest cron — operator visibility |
| TC075 | A.7 | Feedback inbox — SLA enabler |
| TC079 | A.7 | SLA worker alert — promise to user |
| TC092-093 | C.1 + C.4 | Founding invite generation correct |
| TC096 | C.4 | Sequence atomic — founding integrity |
| TC100 | C.4 | compute_discount ready — Phase 5.7 enabler |
| TC105 | Cross | Zalo disabled — channel discipline |
| TC107 | Cross | PII scrub real — privacy promise |
| TC108 | Cross | Founding race condition — scale safety |
| TC117 | Cross | Persona compliance — brand integrity |
| TC120 | Cross | i18n check — code quality |

**Total critical TCs: 20 (must be 100% signed for launch).**

---

*End of Phase 4.1 Test Plan. Last updated: 2026-05-12.*
