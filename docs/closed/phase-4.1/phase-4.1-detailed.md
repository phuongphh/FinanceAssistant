# Phase 4.1 — Pre-Launch Hardening (Revised v2)

> **Prerequisites:** Phase 4A (Financial Twin MVP) + Phase 4B (Twin Polish + Life Events + Cashflow v2 + Zalo OA adapter) shipped và stable trên main.
> **Thời gian:** ~3 tuần (mid-May → early-June 2026).
> **Mục tiêu:** Đưa Bé Tiền sang trạng thái **production-ready cho 50-user Founding Member soft launch trên Telegram** vào tháng 6/2026 — không thêm "wow feature" mới, mà siết 4 trục: (1) first-session UX không lạc, (2) chi phí LLM không nổ, (3) feedback loop và observability đủ để học từ 50 user thật, (4) founding member experience đặt nền cho monetization sau này.
> **"Done":** 50 user Founding Member onboard trong tuần đầu launch, D7 retention ≥ 40%, ≥ 70% user mở Twin trong session đầu, không có incident "LLM cost spike" hoặc "im lặng > 24h với feedback critical".

Phase 4.1 là **bản lề giữa "đã ship hết feature core" và "soft launch tháng 6"**. Phase 4A/4B đã làm Bé Tiền **đủ tính năng** — nhưng "đủ tính năng" không bằng "sẵn sàng cho 50 người lạ chạm vào lần đầu". Phase này tập trung vào 4 mối lo cụ thể:

1. **First impression rủi ro cao:** User mới mở bot không biết bắt đầu từ đâu → bounce trong 5 phút đầu → mất luôn cơ hội thấy Twin (wow-feature).
2. **Cost runaway nguy hiểm:** DeepSeek + Claude OCR + Whisper không có budget cap per user → 1 user spam OCR có thể đốt 10× budget tháng.
3. **Mù khi launch:** Không có Sentry, không có LLM dashboard, không có KPI digest → không biết user đang struggle ở đâu → fix chậm → mất user.
4. **Monetization chưa có scaffolding:** Không có khái niệm "founding member" → khi launch Pro ở Phase 5.7, không phân biệt được cohort sớm với cohort sau → không giữ được lời hứa giảm giá.

---

## 📋 Changelog so với Draft v1

Phase 4.1 được revise sau buổi review chiến lược về UX, pricing, và channel. Tóm gọn những thay đổi:

| Thay đổi | Lý do |
|---|---|
| **A.1 Step 1: bỏ câu hỏi "wealth level"** → thay bằng câu hỏi mục tiêu ("Bạn muốn Bé Tiền giúp gì trước nhất?") | Hỏi thẳng tài sản ngay câu đầu là culture-risk với mass affluent VN. Infer wealth từ Step 2 (asset đầu tiên user nhập) chính xác hơn self-report. |
| **A.1 Demo mode framing** rõ ràng hơn | Tránh user hiểu nhầm 50tr placeholder là Twin thật của mình → loss of trust. |
| **A.2 Twin narrative bằng mascot trước khi hiện chart** | Cone chart là viz lạ với user không phải dân finance. Mascot phải dẫn dắt. |
| **A.2 Resume mechanism nếu user drop > 10 phút** | Drop giữa onboarding là failure mode phổ biến nhất, không thể bỏ qua. |
| **A.2 In-the-moment feedback button sau khi Twin hiện 5–10s** | Khoảnh khắc dopamine cao = qualitative signal tốt nhất. |
| **NEW Story A.8 — First morning briefing onboarding** | Briefing đầu tiên cũng là một "first experience" — cần frame riêng, không assume user biết đọc. |
| **C.1 Acquisition source feed copy** | Source từ `friends` ≠ source từ `vn_finance_community` → welcome copy nên khác nhau. |
| **NEW Story C.4 — Founding Member experience** | Đặt scaffolding cho 50% lifetime discount promise; cần DB flag + welcome copy + operator view. |
| **Channel strategy: Telegram-only cho soft launch** | Telegram adapter đã production-stable; 50 user từ VN finance Telegram community là cohort đúng. Zalo OA defer Phase 5.x với strategy redesigned: Tin Tư vấn 48h window MIỄN PHÍ cho user daily-active = có thể đạt full parity với Telegram về cost (corrected: lúc đầu tưởng phải dùng Mini App vì ZNS đắt, nhưng OA OpenAPI có khung free 48h). |
| **Pricing: single-tier Pro 88k cho v1**, Max defer Phase 5.7+ | Launch Max trước khi feature gate được định = rủi ro tier vô dụng. Single tier dễ communicate, đo sạch. |

---

## 🎯 Triết Lý Thiết Kế

### 1. Polish over feature

Không thêm tính năng mới nào trong phase này. Mọi user story đều phải trả lời "câu hỏi nào về readiness mà phase này giải quyết?" — nếu không có, defer sang sau soft launch.

### 2. First 5 phút quyết định

Wow-moment phải xảy ra trong session đầu, không phải session thứ 3. Onboarding chỉ thành công khi user **thấy Twin của chính mình** (dù chỉ với 1 asset placeholder) trong < 5 phút từ `/start`.

### 3. Cost guardrail là kỷ luật, không phải tuỳ chọn

Budget cap per user phải có **trước** soft launch — không phải khi đã thấy hoá đơn DeepSeek tăng vọt. Default cap rộng tay (đủ cho heavy user thật), nhưng tồn tại để chặn runaway.

### 4. Observability từ ngày đầu

Không launch khi Sentry chưa wire vào tất cả workers. KPI digest daily phải chạy được ngay từ ngày 1 — kể cả khi mới có 1 user — để pattern "có dashboard, có pattern" hình thành sớm.

### 5. Feedback SLA là cam kết với user

Soft launch không cần scale, nhưng cần **chạm tay**: user gửi `/feedback` thì phải có người đọc và phản hồi trong < 24h. Đây không phải tự động hoá — đây là rule cho operator (user/founder). Phase này build công cụ để rule đó dễ giữ.

### 6. Channel discipline: 1 channel cho launch, không 2

Soft launch chỉ chạy trên Telegram. Zalo channel có architecture sẵn (Phase 4B đã ship adapter) nhưng **không activate cho cohort soft launch**. Lý do: học 1 channel cho sạch, đừng đo nhiễu với channel có cost economics khác hẳn.

### 7. Founding cohort là tài sản, không phải user pool tạm

50 user đầu là **Founding Members** — họ được giảm 50% trọn đời khi Pro ra mắt. Phase 4.1 phải có DB scaffolding + welcome copy + operator view cho promise đó, dù Phase 5.7 (monetization) chưa happen.

---

## 📅 Phân Bổ Thời Gian

| Tuần | Trọng tâm | Output chính |
|---|---|---|
| **Tuần 1 (~5 ngày)** | Epic A — Hardening phần 1: onboarding flow + cost guardrails | `/start` flow mới với goal-based step 1, demo mode framing, budget cap middleware, daily cost report |
| **Tuần 2 (~5 ngày)** | Epic A — Hardening phần 2: observability + feedback + first-briefing | Sentry wired, LLM dashboard, KPI digest cron, feedback inbox UI, A.8 first briefing onboarding |
| **Tuần 3 (~5 ngày)** | Epic B — Twin polish thực chiến + Epic C — Soft launch playbook + Founding member scaffolding | Shareable Twin image, predictions-vs-actual, 50-user playbook, founding member DB + copy |

### Critical path

```
A.1 onboarding redesign ── A.2 first-Twin shortcut ── A.8 first briefing onboarding ── E2E first-session test
                                    │
A.3 cost guardrail middleware ── A.4 daily cost report
                                    │
A.5 Sentry + LLM dashboard ── A.6 KPI digest ── A.7 feedback triage UI
                                    │
B.1 shareable Twin image ── B.2 predictions-vs-actual ── ready
                                    │
C.1 acquisition source ── C.4 founding member ── C.2 metrics rubric ── C.3 kill criteria ── launch
```

Critical path = A.1 → A.2 → A.8 → A.5 → A.6 → C.4 → C.2. Tất cả phải xong trước khi soft launch.

---

## 🗂️ Cấu Trúc Thay Đổi

### Files Touched

```
bot/handlers/
├── start_handler.py                          (rewrite: 3-step guided onboarding, goal-based step 1)
├── onboarding_handler.py                     (new: first-asset → first-Twin → first-briefing chain)
├── feedback_handler.py                       (extend: triage commands + in-onboarding feedback button)
└── founding_handler.py                       (new: /whoami, /founding_status for operator)

services/
├── onboarding/
│   ├── onboarding_service.py                 (new: session state machine with resume support)
│   └── wealth_inference_service.py           (new: infer tier from first-asset value, replaces explicit question)
├── cost/
│   ├── budget_service.py                     (new: per-user budget cap logic, free|pro tiers only for v1)
│   └── cost_report_service.py                (new: daily aggregate)
├── twin/
│   ├── twin_share_service.py                 (new: shareable image generation)
│   ├── twin_calibration_service.py           (new: predictions vs actual)
│   └── twin_narrative_service.py             (new: mascot intro before chart render)
├── briefing/
│   └── first_briefing_service.py             (new: special-format first morning briefing with explainer)
├── feedback/
│   └── feedback_triage_service.py            (extend: SLA tracking + inline onboarding feedback)
└── founding/
    └── founding_member_service.py            (new: mark + query founding cohort)

adapters/
├── llm/
│   └── cost_tracking_adapter.py              (new: wrap DeepSeek/Claude/Whisper)
├── observability/
│   ├── sentry_adapter.py                     (new: error capture)
│   └── llm_metrics_adapter.py                (new: per-call timing + token count)
└── image/
    └── twin_image_renderer.py                (new: PIL/Pillow chart-to-image)

workers/
├── cost_budget_worker.py                     (new: enforce cap before LLM call)
├── daily_kpi_digest_worker.py                (new: cron 8:00 → Telegram to operator)
├── feedback_sla_worker.py                    (new: alert if feedback unanswered > 24h)
├── onboarding_resume_worker.py               (new: nudge user if stuck in onboarding > 10 min)
└── twin_calibration_worker.py                (new: fill actual_vnd for due snapshots)

scripts/
├── kpi_digest.py                             (new: standalone runnable)
├── soft_launch_acquisition.py                (new: invite link generator + tracking, with founding flag)
└── twin_calibration_backfill.py              (new: replay past Twin runs)

content/
├── onboarding/
│   ├── welcome_v2.yaml                       (new: 3-step goal-based strings, source-aware copy)
│   ├── first_twin_intro.yaml                 (new: mascot narrative before cone chart)
│   ├── demo_mode_framing.yaml                (new: explicit "this is demo" wrapper)
│   ├── resume_nudge.yaml                     (new: 1-time nudge for stuck users)
│   ├── first_briefing.yaml                   (new: format for briefing #1, with explainer)
│   └── founding_welcome.yaml                 (new: founding member-specific welcome)
└── feedback/
    └── triage_responses.yaml                 (new: templated operator replies)

alembic/versions/
├── 4.1.01_user_cost_budgets.py               (new: per-user budget + spend tracking, free|pro tiers)
├── 4.1.02_feedback_sla_index.py              (new: index for SLA query)
├── 4.1.03_twin_calibration_log.py            (new: predicted vs actual snapshots)
└── 4.1.04_founding_member_flag.py            (new: users.is_founding_member + invite_codes.grants_founding_status)

docs/current/phase-4.1/
├── phase-4.1-detailed.md                     (this file)
├── phase-4.1-issues.md
├── phase-4.1-test-cases.md
├── phase-4.1-deploy-announcements.md
├── success-metrics.md
└── kill-criteria.md
```

---

## 🗄️ Database Schema

### Migration `4.1.01_user_cost_budgets.py`

```sql
CREATE TABLE user_cost_budgets (
    user_id UUID PRIMARY KEY REFERENCES users(id),
    tier VARCHAR(16) NOT NULL DEFAULT 'free',          -- free | pro  (max reserved for Phase 5.7+)
    monthly_cap_vnd NUMERIC(15, 2) NOT NULL,
    current_month_spend_vnd NUMERIC(15, 2) NOT NULL DEFAULT 0,
    current_month_started_at DATE NOT NULL,
    last_warning_sent_at TIMESTAMPTZ NULL,              -- when 80%/100% warning was last delivered
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_tier_v1 CHECK (tier IN ('free', 'pro'))  -- enforce v1 scope
);

CREATE TABLE llm_cost_log (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    provider VARCHAR(32) NOT NULL,                      -- deepseek | claude | whisper
    operation VARCHAR(64) NOT NULL,                     -- classify_intent | ocr_receipt | transcribe
    tokens_in INT NOT NULL DEFAULT 0,
    tokens_out INT NOT NULL DEFAULT 0,
    cost_vnd NUMERIC(15, 4) NOT NULL,
    latency_ms INT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_llm_cost_log_user_day
    ON llm_cost_log(user_id, created_at);
CREATE INDEX idx_llm_cost_log_provider_day
    ON llm_cost_log(provider, created_at);
```

**Lưu ý quan trọng về tier:**
- v1 chỉ có `free` và `pro`. Max defer Phase 5.7+ khi feature gate được định nghĩa.
- Budget cap mặc định: **free = 30,000 VND/tháng** (đủ cho ~500 DeepSeek classify calls), **pro = 100,000 VND/tháng** (đủ cho heavy user trong v1). Tất cả user trong Phase 4.1 = `free` (chưa có payment).
- Mục đích bảng này KHÔNG phải monetize trong Phase 4.1 — mà là **stop the bleeding** nếu 1 user lỡ spam.
- `CHECK CONSTRAINT chk_tier_v1` cố tình hạn chế để bug-prevention. Khi mở Max ở Phase 5.7, sẽ drop constraint trong migration mới.

### Migration `4.1.02_feedback_sla_index.py`

```sql
CREATE INDEX idx_feedback_unanswered_age
    ON feedbacks(created_at)
    WHERE status = 'open';                              -- partial index for SLA query

ALTER TABLE feedbacks
    ADD COLUMN first_responded_at TIMESTAMPTZ NULL,
    ADD COLUMN sla_breach_alerted_at TIMESTAMPTZ NULL,
    ADD COLUMN onboarding_emoji_signal VARCHAR(16) NULL; -- '😍' | '🤔' | '😕' for in-onboarding feedback
```

### Migration `4.1.03_twin_calibration_log.py`

```sql
CREATE TABLE twin_calibration_snapshots (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    predicted_at TIMESTAMPTZ NOT NULL,                  -- when the cone was computed
    horizon_days INT NOT NULL,                          -- 7 | 30 | 90 — check-back window
    p10_vnd NUMERIC(20, 2) NOT NULL,
    p50_vnd NUMERIC(20, 2) NOT NULL,
    p90_vnd NUMERIC(20, 2) NOT NULL,
    actual_vnd NUMERIC(20, 2) NULL,                     -- filled in when horizon hits
    actual_recorded_at TIMESTAMPTZ NULL,
    within_band BOOLEAN NULL,                           -- true if P10 ≤ actual ≤ P90
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_twin_calibration_due
    ON twin_calibration_snapshots(predicted_at, horizon_days)
    WHERE actual_vnd IS NULL;
```

### Migration `4.1.04_founding_member_flag.py`

```sql
-- Mark user as founding member (1 of first 50 soft-launch cohort)
ALTER TABLE users
    ADD COLUMN is_founding_member BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN founding_member_sequence INT NULL,        -- 1..50 cho thứ tự onboard
    ADD COLUMN founding_member_at TIMESTAMPTZ NULL;      -- when they activated invite code

-- Each invite code can grant founding status
ALTER TABLE invite_codes
    ADD COLUMN grants_founding_status BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX idx_users_founding
    ON users(is_founding_member)
    WHERE is_founding_member = TRUE;

-- Onboarding session state (for resume mechanism)
CREATE TABLE onboarding_sessions (
    user_id UUID PRIMARY KEY REFERENCES users(id),
    started_at TIMESTAMPTZ NOT NULL,
    current_step VARCHAR(32) NOT NULL,                  -- 'goal_question' | 'first_asset' | 'twin_shown' | 'completed'
    goal_choice VARCHAR(32) NULL,                       -- 'understand_wealth' | 'plan_goal' | 'track_spending'
    inferred_wealth_segment VARCHAR(32) NULL,           -- starter | young_pro | mass_affluent | hnw
    first_twin_shown_at TIMESTAMPTZ NULL,
    nudge_sent_at TIMESTAMPTZ NULL,                     -- when resume nudge was sent (1-time)
    completed_at TIMESTAMPTZ NULL,
    onboarding_feedback_signal VARCHAR(16) NULL,        -- emoji from in-the-moment feedback
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_onboarding_stuck
    ON onboarding_sessions(updated_at)
    WHERE current_step != 'completed' AND nudge_sent_at IS NULL;
```

---

## 🔧 Epic A — Pre-Launch Hardening

**Goal:** Đưa onboarding, cost control, observability, và feedback triage lên mức production-grade. Đây là core của Phase 4.1 (~1.5 tuần).

**Stories:** A.1 → A.8 (8 stories)

### Story A.1 — Onboarding redesign (3-step goal-based flow)

**Layer:** `bot/handlers/start_handler.py` + `content/onboarding/welcome_v2.yaml` + `services/onboarding/onboarding_service.py`

**Acceptance:**
- `/start` lần đầu hiển thị message ngắn (< 200 chars) giới thiệu Bé Tiền + inline button "🌱 Bắt đầu hành trình".
- Sau khi bấm, dẫn user qua 3 bước với thanh tiến trình `(1/3)` `(2/3)` `(3/3)` ở đầu mỗi message.
- **Step 1 — Câu hỏi mục tiêu (không phải wealth level):** *"Bạn muốn Bé Tiền giúp gì trước nhất?"* với 3 inline button:
  - 🌱 *"Hiểu rõ tổng tài sản của tôi"* → `goal_choice = understand_wealth`
  - 🎯 *"Lên kế hoạch cho mục tiêu lớn"* (mua nhà, nghỉ hưu, học phí con) → `goal_choice = plan_goal`
  - 📊 *"Theo dõi chi tiêu thông minh"* → `goal_choice = track_spending`
- **Step 2 — Thêm asset đầu tiên:** prompt user nhập số tiền tiết kiệm/đầu tư hiện tại (free text VND), hoặc bấm nút *"Để Bé Tiền dùng demo trước"* để skip.
- **Demo mode framing rõ ràng:** Khi user skip Step 2, message tiếp theo bắt đầu với banner *"📌 Demo Mode — đây là Twin của một người giả định với 50tr tiết kiệm. Twin của bạn sẽ khác — nhập tài sản thật để xem Twin riêng của bạn."* Sau khi xem demo, có CTA cứng *"💎 Xem Twin của tôi"* dẫn user quay lại Step 2.
- **Wealth segment inference:** Sau Step 2 (asset thật), service `wealth_inference_service` map giá trị sang segment:
  - < 100tr → `starter`
  - 100tr–500tr → `young_pro`
  - 500tr–5 tỷ → `mass_affluent`
  - > 5 tỷ → `hnw`
- **Step 3 — Mở Twin đầu tiên:** auto-trigger (xem A.2).
- Toàn bộ string nằm trong `welcome_v2.yaml`, không hardcode.
- Acquisition source-aware welcome: nếu user vào từ invite link với `source=friends`, welcome message bổ sung *"[Tên người giới thiệu] giới thiệu bạn đến với Bé Tiền — cảm ơn bạn dành thời gian thử nhé."* Nếu `source=vn_finance_community`, copy có tone professional hơn. Mapping source → copy variant lưu trong `welcome_v2.yaml`.

### Story A.2 — First-Twin shortcut + narrative + in-moment feedback

**Layer:** `services/onboarding/onboarding_service.py` + `services/twin/twin_narrative_service.py` + `bot/handlers/onboarding_handler.py` + `workers/onboarding_resume_worker.py`

**Acceptance:**
- Sau khi user hoàn tất Step 2, service auto-trigger Twin computation và push kết quả qua 3 message liên tiếp:
  1. **Mascot narrative:** *"Đây là Twin tài chính của bạn — Bé Tiền vẽ ra 3 con đường tương lai dựa trên tình hình hiện tại. Đường giữa là điều kiện thường. Đường trên là nếu bạn tiết kiệm chăm hơn. Đường dưới là nếu có biến cố. Bạn không cần đoán tương lai — Bé Tiền đoán giúp, bạn chỉ cần quyết định."* (string trong `first_twin_intro.yaml`)
  2. **Cone chart image** (render từ existing twin engine).
  3. **In-moment feedback prompt** (sau 5–10 giây delay): *"💬 Bạn cảm thấy thế nào về Twin đầu tiên?"* với 3 inline button emoji (😍 / 🤔 / 😕). Bấm vào lưu signal vào `onboarding_sessions.onboarding_feedback_signal` và `feedbacks.onboarding_emoji_signal`. Cũng acknowledge bằng 1 message ấm áp ("Cảm ơn bạn — Bé Tiền ghi nhận để cải thiện").
- **Time-to-first-Twin** từ `/start` đến message cone chart ≤ 5 phút (đo bằng `started_at` và `first_twin_shown_at` trong `onboarding_sessions`).
- **Fallback nếu Twin compute fail:** message giải thích *"Bé Tiền đang tính, bạn quay lại sau 1 phút nhé"* — KHÔNG để user ngồi nhìn `...` 30s.
- **Resume mechanism (worker `onboarding_resume_worker`):**
  - Worker chạy mỗi 5 phút, query `onboarding_sessions` WHERE `current_step != 'completed'` AND `nudge_sent_at IS NULL` AND `updated_at < NOW() - 10 minutes`.
  - Gửi **1 message duy nhất** qua Notifier: *"Bé Tiền đang chờ bạn ở bước [X] — chỉ cần thêm 1 thông tin là Twin sẵn sàng. Tiếp tục nhé?"* với 2 button *"Tiếp tục"* và *"Để Bé Tiền dùng demo trước"*.
  - Set `nudge_sent_at = NOW()` để không gửi lần 2.
- **Completion event** log vào `intent_logs` với action `(onboarding, completed)` và metadata `{goal: <choice>, segment: <inferred>}`.

### Story A.3 — Cost guardrail middleware

**Layer:** `services/cost/budget_service.py` + `adapters/llm/cost_tracking_adapter.py` + `workers/cost_budget_worker.py`

**Acceptance:**
- Mọi LLM call đi qua `cost_tracking_adapter` wrap quanh DeepSeek/Claude/Whisper adapter hiện có.
- Trước mỗi call, service kiểm tra `user_cost_budgets.current_month_spend_vnd` < `monthly_cap_vnd`.
- Nếu đã chạm 80%: gửi message warning ấm áp cho user (1 lần/tháng, lưu `last_warning_sent_at`), tiếp tục cho qua.
- Nếu chạm 100%: từ chối call, raise `BudgetExceededError`. Service xử lý, trả message qua content yaml: *"Tháng này Bé Tiền tạm dừng tính năng X cho bạn — sang tháng mở lại nhé. Có gì cần gấp dùng /feedback Bé Tiền xem qua."*
- Mỗi call success log vào `llm_cost_log` với provider/operation/tokens/cost/latency.
- Budget cap mặc định (v1): **free = 30,000 VND/tháng**, **pro = 100,000 VND/tháng** (chưa active trong Phase 4.1, để sẵn cho 5.7).
- Operator command `/budget_set <user_id> <amount>` để override per-user khi cần (vd: heavy legit user).

### Story A.4 — Daily cost report

**Layer:** `services/cost/cost_report_service.py` + `scripts/kpi_digest.py` (shared cron)

**Acceptance:**
- Mỗi sáng 8:00 ICT, operator nhận message Telegram tổng hợp 24h trước:
  - Tổng cost theo provider (DeepSeek / Claude OCR / Whisper)
  - Top 5 user theo cost
  - User mới chạm 80% cap trong ngày
- Format ngắn (< 500 chars), số liệu round về 1k VND.
- Nếu tổng cost ngày > 200% trung bình 7 ngày trước → flag 🚨 ở đầu message.
- Merge vào cùng 1 message với KPI digest (Story A.6) để operator chỉ đọc 1 message/sáng.

### Story A.5 — Sentry + LLM metrics dashboard

**Layer:** `adapters/observability/sentry_adapter.py` + `adapters/observability/llm_metrics_adapter.py`

**Acceptance:**
- Sentry SDK wire vào FastAPI app + tất cả worker. Mọi unhandled exception capture với user_id + intent context.
- **PII scrub trước khi gửi Sentry** (beforesend hook):
  - Strip số > 6 chữ số (loại tiền cụ thể của user)
  - Strip email/phone bằng regex
  - Whitelist field thay vì blacklist — chỉ pass fields `intent_type`, `step`, `error_message_template_id`
- LLM metrics adapter ghi mỗi call: provider, operation, latency_ms, success/error, model_version → insert vào `llm_cost_log` (đã có Story A.3).
- Operator có dashboard (Metabase với connection trực tiếp PostgreSQL) hiển thị: error rate per intent, p50/p95 LLM latency, daily active users.
- ENV var `SENTRY_DSN` documented trong `.env.example`, không hardcode.

### Story A.6 — Daily KPI digest cron

**Layer:** `workers/daily_kpi_digest_worker.py` + `scripts/kpi_digest.py`

**Acceptance:**
- Cron chạy 8:00 ICT mỗi sáng, gửi **1 message duy nhất** Telegram đến operator (user_id từ ENV `OPERATOR_TELEGRAM_ID`).
- Nội dung gộp (Story A.4 cost + KPI):
  - **Cost section:** Tổng cost 24h, top 5 user, user chạm 80%
  - **Engagement section:** DAU/WAU/MAU, số Twin view 24h, số onboarding completed
  - **Quality section:** Intent classification accuracy (% confirm vs % clarify), in-onboarding feedback emoji breakdown (😍/🤔/😕)
  - **Churn signals:** User không active 7+ ngày (gồm founding members nếu có)
  - **Feedback queue:** Top 3 feedback chưa trả lời với age
- Nếu cron fail → Sentry alert (không silent).

### Story A.7 — Feedback triage UI

**Layer:** `bot/handlers/feedback_handler.py` (extend) + `services/feedback/feedback_triage_service.py` + `content/feedback/triage_responses.yaml`

**Acceptance:**
- Operator command `/feedback_inbox` liệt kê tất cả feedback `status=open` sắp xếp theo `created_at` cũ nhất trước.
- Mỗi feedback hiển thị: ID ngắn, user wealth segment + founding flag (nếu có), snippet 100 chars, age ("2h trước", "1 ngày trước"), in-onboarding emoji signal nếu có.
- Operator có thể reply bằng `/feedback_reply <id> <message>` — service gửi message đó cho user via Notifier, đánh dấu `first_responded_at = NOW()`, set `status = answered`.
- Có 5 template phản hồi nhanh trong `triage_responses.yaml`:
  - `thanks_logged` — "Cảm ơn bạn — Bé Tiền đã ghi nhận và đang xem qua."
  - `clarify_request` — "Bạn cho Bé Tiền biết thêm về [X] được không?"
  - `feature_acknowledged` — "Ý tưởng hay — Bé Tiền lưu vào roadmap."
  - `bug_apology` — "Xin lỗi bạn, đây là bug đang fix — kết quả sẽ có trong 24h."
  - `not_supported_yet` — "Tính năng này chưa có nhưng đang trong kế hoạch — Bé Tiền sẽ báo khi sẵn sàng."
- Worker `feedback_sla_worker` chạy mỗi giờ: nếu có feedback `status=open` quá 24h → gửi alert đến operator (chỉ alert 1 lần per feedback, set `sla_breach_alerted_at`).

### Story A.8 — First morning briefing onboarding [NEW]

**Layer:** `services/briefing/first_briefing_service.py` + `content/onboarding/first_briefing.yaml`

**Acceptance:**
- Service detect user nhận briefing lần đầu (query `briefing_logs` đếm count cho user_id, nếu = 1 thì áp first-briefing format).
- First briefing format khác briefing thường:
  - Mở đầu bằng explainer ngắn: *"Đây là briefing đầu tiên của bạn! Mỗi sáng 8h Bé Tiền sẽ tổng hợp 3 thứ quan trọng nhất về tài sản của bạn trong 30 giây đọc. Hôm nay Bé Tiền nói về:"*
  - 3 mục briefing bình thường (cùng format briefing routine)
  - Kết thúc bằng inline button "💡 Bé Tiền đang nói gì?" → khi bấm, hiện explanation chi tiết của từng metric.
- First briefing gửi 8h sáng **ngày sau onboarding**, không gửi liền sau onboarding (tránh spam) và **không apply smart logic** (gửi đúng 8h sáng hôm sau bất kể user onboard giờ nào). Logic đơn giản — nếu user mute notification, briefing vẫn nằm trong chat khi họ mở lại.
- Log first briefing event vào `intent_logs` với action `(briefing, first_shown)`.

---

## 🔧 Epic B — Twin Polish Thực Chiến

**Goal:** Lấy 2 user request lớn nhất từ Phase 4A dogfood — "muốn share Twin của mình" và "Twin đoán có đúng không?" — để build trust trước launch.

**Stories:** B.1 → B.2 (2 stories, ~1 tuần)

### Story B.1 — Shareable Twin image

**Layer:** `services/twin/twin_share_service.py` + `adapters/image/twin_image_renderer.py`

**Acceptance:**
- Trong Twin view (Telegram), thêm nút "📸 Lưu thành ảnh" — bấm vào trả về PNG render của cone chart + summary text overlay.
- Image **không** chứa số tiền tuyệt đối (kể cả P50). Chỉ hiển thị: % tăng trưởng, time horizon, watermark "Bé Tiền — Personal CFO".
- User có thể save về máy hoặc share — Bé Tiền **không** chủ động prompt share lên FB/Zalo (per Vietnamese cultural fit).
- Render dùng PIL/Pillow, không depend vào headless browser → < 1s/image.
- Background gradient + Bé Tiền mascot góc dưới phải.
- Nếu user là founding member, image có thêm badge nhỏ góc trên trái "🌱 Founding Member".

### Story B.2 — Predictions vs actual

**Layer:** `services/twin/twin_calibration_service.py` + `scripts/twin_calibration_backfill.py` + `workers/twin_calibration_worker.py`

**Acceptance:**
- Mỗi lần user mở Twin, service log snapshot vào `twin_calibration_snapshots` với 3 horizon: 7d, 30d, 90d.
- Worker chạy daily: với mỗi snapshot đến hạn, fill `actual_vnd` từ current net worth, compute `within_band`.
- Trong Twin view, thêm section "🎯 Bé Tiền đoán đúng bao nhiêu?" hiển thị % within-band của user (chỉ hiện khi có ≥ 3 snapshot completed).
- Honest framing: *"Bé Tiền đoán đúng 7/9 lần (78%)"* — KHÔNG inflate.
- Nếu hit-rate < 50%: hiển thị disclaimer *"dự phóng chưa chuẩn, Bé Tiền đang học thêm"* thay vì trốn số.

---

## 🔧 Epic C — Soft Launch Playbook & Founding Cohort

**Goal:** Operator có công cụ + tiêu chí rõ ràng để chạy 50-user soft launch trên Telegram, và scaffolding cho founding member promise.

**Stories:** C.1 → C.4 (4 stories, ~4-5 ngày)

### Story C.1 — Acquisition source + invite tracking + source-aware copy

**Layer:** `scripts/soft_launch_acquisition.py` + `bot/handlers/start_handler.py` (extend) + `content/onboarding/welcome_v2.yaml`

**Acceptance:**
- Script generate 50 unique invite link `t.me/BeTienBot?start=invite_<token>` với metadata (source, batch_name, **grants_founding_status=TRUE**) lưu vào table `invite_codes`.
- Khi user mới start bot với token:
  - Log source vào `users.acquisition_source`
  - Nếu invite code có `grants_founding_status=TRUE`: set `users.is_founding_member=TRUE`, assign next `founding_member_sequence` (atomic counter 1..50), set `founding_member_at=NOW()` (xem Story C.4 chi tiết).
- Operator có command `/cohort_stats` xem breakdown user theo source.
- Source ban đầu: `friends`, `personal_fb`, `vn_finance_community`, `direct_msg`, `tg_finance_groups`.
- **Source-aware welcome copy mapping** trong `welcome_v2.yaml`:
  - `friends` / `personal_fb` → warm tone: *"[Tên người giới thiệu] mời bạn — cảm ơn bạn dành thời gian thử Bé Tiền nhé."*
  - `vn_finance_community` / `tg_finance_groups` → professional tone: *"Cảm ơn bạn đến từ cộng đồng tài chính. Bé Tiền là Personal CFO cho người Việt mass affluent."*
  - `direct_msg` → personal tone: *"Cảm ơn bạn đã trả lời tin nhắn của Bé Tiền — bắt đầu khám phá nhé!"*
- Output script: CSV 50 dòng với `invite_url`, `source`, `batch_name` để operator distribute.

### Story C.2 — Success metrics rubric

**Layer:** Documentation only — output: `docs/current/phase-4.1/success-metrics.md`.

**Acceptance:**
- Document 6 metric với target + measurement method + cron để compute:
  - **D1 retention ≥ 70%**: % founding member quay lại trong ngày 2 sau onboard
  - **D7 retention ≥ 40%**: % founding member active trong tuần 2
  - **% user mở Twin trong session đầu ≥ 70%**: từ `onboarding_sessions.first_twin_shown_at IS NOT NULL`
  - **% user log ≥ 1 asset thật trong 7 ngày đầu ≥ 60%**: từ `assets` table, exclude placeholder rows
  - **Intent classification accuracy ≥ 85%**: từ `intent_logs` (% confirmed vs clarified vs misexecuted)
  - **Feedback SLA (response < 24h) ≥ 95%**: từ `feedbacks.first_responded_at - created_at`
- Bổ sung 2 metric mới về founding cohort:
  - **In-onboarding feedback signal distribution**: % 😍 vs 🤔 vs 😕 — target 😍 ≥ 50%
  - **Twin satisfaction sau D7**: qualitative interview với 10 founding member ngẫu nhiên
- Mỗi metric link đến SQL query để compute từ existing tables.

### Story C.3 — Kill criteria

**Layer:** Documentation only — output: `docs/current/phase-4.1/kill-criteria.md`.

**Acceptance:**
- Document tiêu chí dừng/pivot rõ ràng:
  - **4-week retention < 20%** → pivot positioning hoặc kill product
  - **Cost per active user > 50k VND/tháng** sau 1 tháng → re-evaluate LLM budget hoặc model choice
  - **Critical bug rate (Sentry P1) > 1/day** với cohort 50 user → freeze feature, fix sprint
  - **Bé Tiền persona violation reported > 5 lần/tuần** → prompt audit toàn bộ
  - **In-onboarding emoji signal 😕 > 30%** trong 50 founding member → first-impression broken, redesign A.1+A.2 trước khi mở rộng
  - **Twin within-band hit rate < 40%** sau 90 ngày → calibration model needs rework
- Mỗi tiêu chí có owner (operator/PM), threshold rõ ràng, action plan.

### Story C.4 — Founding Member experience [NEW]

**Layer:** `services/founding/founding_member_service.py` + `bot/handlers/founding_handler.py` + `content/onboarding/founding_welcome.yaml`

**Acceptance:**
- **Founding welcome banner:** User vào từ invite code với `grants_founding_status=TRUE` thấy welcome message bổ sung:
  > *"🌱 Bạn là Founding Member #[N] của Bé Tiền — 1 trong 50 người đầu tiên.*
  > *Trong giai đoạn này toàn bộ tính năng miễn phí.*
  > *Khi Bé Tiền Pro ra mắt chính thức (dự kiến cuối 2026), bạn được giảm 50% trọn đời — 44.000đ/tháng thay vì 88.000đ — để cảm ơn sự đồng hành."*
- **User profile command `/whoami`:** trả về thông tin user gồm wealth segment, onboarding date, founding member sequence (nếu có), days active.
- **Operator command `/founding_status`:** liệt kê 50 founding member với thứ tự, ngày onboard, days active, last seen.
- **Sequence assignment atomic:** dùng PostgreSQL `SELECT ... FOR UPDATE` hoặc advisory lock để tránh race condition khi 2 user redeem cùng lúc.
- **Founding badge** xuất hiện trong:
  - Welcome message
  - `/whoami` output
  - Shareable Twin image (góc trên trái — xem B.1)
  - Operator feedback inbox (gắn flag khi đọc feedback từ founding member)
- **Lưu ý quan trọng về promise:** Phase 4.1 KHÔNG ship payment. 50% discount sẽ apply khi Phase 5.7 (Monetization) ra mắt — service `founding_member_service.compute_discount(user_id)` đã có sẵn để Phase 5.7 dùng. Đây là **lời hứa cần giữ** — operator phải document promise rõ ràng, không quên.

---

## 📞 Channel Strategy — Telegram-Only Soft Launch (Zalo Full-Parity về sau)

Phase 4.1 ship **chỉ trên Telegram**. Đây là quyết định focus cho soft launch, KHÔNG phải đánh giá thấp Zalo. Zalo OA sẽ là **primary channel cho mass scale** ở Phase 5.x, với strategy được redesign sau khi xác định đúng cost model.

### Hiểu lại cost model Zalo OA (theo official docs, hiệu lực 01/01/2026)

Tin nhắn OA chia thành các loại với cost rất khác nhau:

| Loại tin | Điều kiện gửi | Phí |
|---|---|---|
| **Tin Tư vấn** (trong 48h từ user interaction cuối) | User đã interact với OA trong 48h | **MIỄN PHÍ** ✅ |
| **Tin Tư vấn** (48h đến 7 ngày) | User interact trong 7 ngày gần nhất | Tính phí theo bảng giá Zalo |
| **Tin Tư vấn** (sau 7 ngày) | Không gửi được qua API consultation | Phải dùng ZNS hoặc Broadcast |
| **ZBS Template Message** (ZNS) | Template đã approve, user có phone trên Zalo | ~200đ/msg gửi thành công |
| **Broadcast** | User đã follow OA | Quota theo gói OA package |

**Insight quan trọng:** Với user **daily active**, briefing 8h sáng nằm trong khung 48h → **hoàn toàn free**. Bé Tiền có thể đạt full parity với Telegram về cost cho user engaged. Vấn đề CHỈ xảy ra khi user disengage > 48h.

### Solution pattern cho 48h window (Phase 5.x design)

Đây là thiết kế cho Phase 5.x khi mở Zalo, không phải Phase 4.1 — nhưng document ở đây để Phase 5.x kickoff có direction:

1. **Mỗi briefing có inline button "đã xem"** — user bấm = tương tác → window reset thêm 48h. Tăng tỷ lệ active interaction một cách tự nhiên.
2. **Track `users.last_interaction_at` per channel** — biết user đang ở zone nào (green: <48h, yellow: 48h-7d, red: >7d).
3. **Yellow zone strategy** — vẫn gửi briefing nhưng tracking cost; nếu cost spike → fallback message ngắn hơn.
4. **Red zone strategy** — không spam ZNS. Gửi **1 ZNS re-engagement** trong tháng với content transactional ("Tài sản của bạn tháng qua có cập nhật mới — vào Bé Tiền xem"). Sau 3 lần ZNS không phản hồi → đánh dấu churned, dừng push.
5. **Streak gamification nhẹ** — *"Bé Tiền và bạn đã đồng hành 14 ngày liên tiếp"* — tăng motivation interact mỗi ngày, giữ window xanh.

### Tại sao vẫn Telegram-only cho Phase 4.1

Dù Zalo OA có thể full-parity về cost, Phase 4.1 vẫn cố tình ship Telegram-only vì 3 lý do:

1. **Telegram adapter đã production-stable.** Phase 4A/4B đã dogfood Telegram nhiều tháng. Zalo OA adapter từ Phase 4B chưa được production-tested với cohort thật — soft launch không phải lúc để test adapter mới.
2. **50 user là cohort nhỏ — focus quan trọng hơn reach.** Distribute 50 invite qua VN finance Telegram communities là path of least resistance. Họ là early adopter persona, có sẵn trên Telegram, không cần thuyết phục.
3. **Học 1 channel cho sạch trước khi mở 2.** Baseline metrics (D1/D7 retention, cost per user, in-onboarding emoji signal) đo trên 1 channel → so sánh được khi mở Zalo Phase 5.x.

### Zalo & Native App — Updated Roadmap

- **Phase 5.1–5.3 (Zalo OA rollout):** Strategy revised — **Zalo OA full-parity với Telegram** với 48h window engagement design (xem solution pattern ở trên). Cần audit Phase 4B Zalo adapter status đầu Phase 5.1. Nếu adapter đã có nhưng chưa implement 48h tracking → bổ sung. Mini App architecture optional, không phải mandatory.
- **Phase 6+ (Native mobile app):** Defer ít nhất 12 tháng. Native app chỉ làm khi PMF proven (Pro conversion ≥ 3%, DAU ≥ 40%) và unit economics justify CPI ($1–3 USD trong VN). Khi đó native app là Max tier feature, không phải acquisition channel.

---

## 💰 Pricing Strategy (Reference cho Phase 5.7)

Phase 4.1 KHÔNG ship paywall. Section này document quyết định pricing đã thảo luận để Phase 5.7 thực thi đúng:

| Tier | Giá | Scope v1 |
|---|---|---|
| Free | 0đ | Default cho tất cả user soft launch |
| Pro | 88.000đ/tháng | Active từ Phase 5.7 |
| Max | 188.000đ/tháng | **Defer** đến khi feature gate được định nghĩa rõ |
| Founding Pro | 44.000đ/tháng | Pro với giảm 50% trọn đời cho 50 founding member |

**Anchor framing cho Pro 88k** (sẽ dùng ở paywall copy Phase 5.7):
- Per-day: *"3.000đ/ngày — rẻ hơn 1 ly cà phê"*
- Comparative: *"Tư vấn 1 tiếng với chuyên viên ngân hàng = 1–3 triệu. Bé Tiền 24/7 = 88k/tháng."*
- Annual: cân nhắc discount 15–20% (88k×12 = 1,056k → annual 850–900k)

**Max tier defer lý do:**
- Single-tier launch dễ communicate, đo conversion sạch
- 2.14x ratio (88→188) OK nhưng cần feature gate rõ — chưa có ở Phase 4.1
- Max sẽ tốt khi có element "human in the loop" (vd: monthly 30-phút chat advisor) hoặc multi-portfolio (family wealth)
- Add Max ở Phase 5.8+ sau khi học được Pro user dùng gì nhiều nhất

**Founding member promise — tracking:**
- DB column `is_founding_member` + `founding_member_sequence` (Phase 4.1)
- Service `compute_discount(user_id)` ready cho Phase 5.7
- Operator phải log promise vào internal doc, không quên khi Pro launch

---

## 📐 Layer Mapping & Contract Compliance

| Story | Routers | Workers | Handlers | Services | Adapters |
|---|---|---|---|---|---|
| A.1 onboarding | — | — | `start_handler`, `onboarding_handler` | `onboarding_service`, `wealth_inference_service` | Notifier |
| A.2 first-Twin + narrative + feedback | — | `onboarding_resume_worker` | `onboarding_handler` | `onboarding_service` → `twin_engine_service`, `twin_narrative_service` | Notifier |
| A.3 cost guardrail | — | `cost_budget_worker` | — (middleware) | `budget_service` | `cost_tracking_adapter` wraps DeepSeek/Claude/Whisper |
| A.4 daily cost report | — | `daily_kpi_digest_worker` | — | `cost_report_service` | Notifier |
| A.5 Sentry | (init) | (init) | — | — | `sentry_adapter`, `llm_metrics_adapter` |
| A.6 KPI digest | — | `daily_kpi_digest_worker` | — | (composes existing services) | Notifier |
| A.7 feedback triage | — | `feedback_sla_worker` | `feedback_handler` (extend) | `feedback_triage_service` | Notifier |
| A.8 first briefing | — | (existing briefing worker, branch on count) | — | `first_briefing_service` | Notifier |
| B.1 share image | — | — | (button on existing Twin view) | `twin_share_service` | `twin_image_renderer` (PIL) |
| B.2 calibration | — | `twin_calibration_worker` | — | `twin_calibration_service` | — |
| C.1 invite tracking + source copy | — | — | `start_handler` (extend) | — | — |
| C.4 founding member | — | — | `start_handler` (extend), `founding_handler` | `founding_member_service` | — |

**Contract checks:**
- `cost_tracking_adapter` chặn LLM call → phải raise domain exception (`BudgetExceededError`), service xử lý + return user-facing message qua content yaml. KHÔNG để adapter gọi Telegram trực tiếp.
- `budget_service` chỉ `flush`, không `commit`. Worker `cost_budget_worker` commit tại boundary.
- `founding_member_service.assign_sequence()` phải dùng row-level lock hoặc advisory lock — không để 2 invite redeem cùng giây gây duplicate sequence.
- Sentry init phải xảy ra trước khi router/worker dispatch — đặt trong `main.py` lifecycle hook.
- `wealth_inference_service` là pure function (no DB write) — gọi từ `onboarding_service`, không gọi từ handler.
- Toàn bộ Vietnamese string trong `content/*.yaml` — check bằng `vi-localization-checker` agent trước merge.
- `twin_narrative_service` là composer pattern — không gọi LLM, chỉ format string từ yaml + inject user-specific values.

---

## ⚠️ Risk & Rollback

| Risk | Severity | Mitigation | Rollback |
|---|---|---|---|
| Onboarding mới làm rối user cũ | Medium | Detect `users.created_at < phase_4_1_deploy_date` → vẫn dùng flow cũ; chỉ user mới mới qua `welcome_v2` | Feature flag `ONBOARDING_V2_ENABLED` env, set false |
| Wealth inference từ asset đầu sai segment | Medium | Buckets rộng tay (<100tr/100-500/500-5tỷ/>5tỷ); user có thể correct sau qua `/profile`; segment chỉ ảnh hưởng content tone, không ảnh hưởng Twin math | Reset segment qua SQL, user gửi `/start` lại |
| Resume nudge gây cảm giác spam | Low | Cap 1 lần/user vĩnh viễn (`nudge_sent_at` check); ngôn ngữ ấm áp, không pushy | Disable worker `onboarding_resume_worker` |
| In-onboarding feedback button bị bấm nhầm | Low | Acknowledge nhẹ ("đã ghi nhận"), không block flow; signal chỉ là quantitative aggregation | Drop column nếu cần (data loss minor) |
| Budget cap chặn nhầm user đang dùng nhiều legit | High | Default cap rộng tay; operator command `/budget_set <user> <amount>` để bump 1-1; warning 80% trước khi block | Bypass cho all = set `monthly_cap_vnd = 999999` qua SQL |
| Sentry leak PII (user message, money) | High | Beforesend hook scrub: regex strip số > 6 digit, strip email/phone; whitelist field thay vì blacklist | Disable Sentry qua env `SENTRY_DSN=""` |
| First briefing format khác làm user confuse | Low | Explainer rõ ràng + button "Bé Tiền đang nói gì?"; chỉ 1 lần đầu | Feature flag `FIRST_BRIEFING_FORMAT_ENABLED` |
| Founding sequence race condition (2 user redeem cùng giây) | Medium | Advisory lock hoặc `SELECT ... FOR UPDATE` trong service | Manual fix qua SQL nếu sequence duplicate |
| Founding member promise quên khi Phase 5.7 | High | `founding_member_service.compute_discount()` ready từ 4.1; document promise trong `/docs/current/founding-promise.md`; checklist trong Phase 5.7 detailed | Honor promise manually qua operator nếu code miss |
| Shareable image làm leak privacy | Medium | Không hiện số tuyệt đối + watermark + user phải tự bấm save (không auto-share) | Disable button qua feature flag |
| Calibration honest framing demotivate user | Low | Chỉ hiện khi ≥ 3 snapshot, ngôn ngữ "Bé Tiền đang học" thay vì "Bé Tiền đoán sai" | Hide section qua feature flag, vẫn log snapshot |
| KPI digest spam operator | Low | Throttle: 1 message/ngày max, gộp tất cả info | Disable cron |
| Zalo adapter từ Phase 4B accidentally activated | High | Feature flag `ZALO_CHANNEL_ENABLED=false` cứng trong deploy config; verify trước khi launch | Set flag = false |

---

## ✅ Definition of Done

- [ ] Tất cả Story A.1–A.8, B.1–B.2, C.1–C.4 acceptance criteria pass.
- [ ] Migration `4.1.01`, `4.1.02`, `4.1.03`, `4.1.04` applied trên dev + staging.
- [ ] Test cases `phase-4.1-test-cases.md` pass với 5 persona; signoff marker = `signed`.
- [ ] `vi-localization-checker` agent pass — không có hardcoded Vietnamese string trong code.
- [ ] `layer-contract-checker` agent pass — service không có `db.commit()`, adapter không có business logic.
- [ ] Sentry capture ít nhất 1 test exception trong staging với PII scrub verified.
- [ ] KPI digest đã chạy 3 ngày liên tiếp trên staging với data thật.
- [ ] Operator đã test flow: `/feedback_inbox` → `/feedback_reply` → user nhận message.
- [ ] Cost report cho ngày test có ≥ 1 LLM call → cost > 0 → log đầy đủ.
- [ ] First-session test: clean account → `/start` → < 5 phút thấy Twin (đo trên staging) — chạy với 3 trong số 3 wealth segment khác nhau.
- [ ] Resume nudge test: tạo user, drop ở step 2, đợi 10 phút → nhận đúng 1 nudge, không 2.
- [ ] Demo mode test: skip Step 2 → thấy banner "Demo Mode" rõ ràng → bấm "Xem Twin của tôi" → quay lại Step 2.
- [ ] First briefing test: clean account onboard hôm nay → 8h sáng mai nhận first briefing với explainer (không phải briefing thường).
- [ ] Founding sequence test: redeem 5 invite code song song → tất cả nhận sequence 1..5 không trùng.
- [ ] `success-metrics.md` + `kill-criteria.md` + `founding-promise.md` đã commit.
- [ ] 50 invite link đã generate với `grants_founding_status=TRUE`, lưu vào DB, in CSV cho operator distribute.
- [ ] Deploy announcement teaser/launch/followup đã preview qua `--dry-run` với operator account.
- [ ] `ZALO_CHANNEL_ENABLED=false` verify trong deploy config.

---

## 🚧 Out of Scope

Phase 4.1 cố tình **không** làm những việc sau (defer hoặc đã có phase riêng):

- ❌ **Payment infrastructure / paywall UI** → Phase 5.7 (Monetization Infra). Founding member promise được track sẵn, không có thanh toán thực.
- ❌ **Max tier feature gate + UI** → Phase 5.8+. Schema chỉ allow `free|pro` qua CHECK constraint.
- ❌ **Zalo channel activation** → Phase 5.1–5.3 với strategy redesigned (Zalo OA full-parity với 48h window engagement). Adapter từ Phase 4B remain in repo nhưng disabled qua feature flag.
- ❌ **Native mobile app** → Phase 6+, chỉ khi PMF proven.
- ❌ **Achievement/badge system** → Phase 5.4 (founding badge là 1 lần, không phải hệ thống).
- ❌ **Life event simulator polish nâng cao** → đã ship trong 4B, không touch lại.
- ❌ **Multi-tier user UI/flow phức tạp** → table có sẵn, UI defer.
- ❌ **Notion dashboard upgrade** → giữ nguyên Phase 3A.
- ❌ **Tính năng "social" (leaderboard, friend share)** → Vietnamese cultural fit nói KHÔNG.
- ❌ **Refactor lớn services/twin/** — Phase 4A vừa ship, chỉ thêm, không sửa.
- ❌ **Audit Phase 4B Zalo OA adapter** → defer sang kickoff Phase 5.1 (riêng task, không gộp 4.1).

---

## 🧭 Recommendations

1. **Tuần 1 dồn force lên A.1 + A.2 + A.8.** Onboarding là phần dễ trượt timeline nhất vì cần dogfood nhiều lần. Mỗi developer commit thử `/start` từ clean account ít nhất 1 lần/ngày — kể cả với cả 3 goal choice variant. A.8 cần dogfood "ngày tiếp theo" nên bắt đầu sớm.

2. **A.3 cost guardrail viết test trước.** Đây là middleware đụng tất cả LLM call — bug ở đây = LLM call fail toàn bộ. Viết integration test với mock DeepSeek + mock budget trước khi wire production.

3. **A.5 Sentry — đừng để cuối cùng.** Wire Sentry ngay tuần 1 (1–2h work). Mọi bug fix sau đó sẽ có stack trace tốt hơn → tiết kiệm thời gian dogfood.

4. **B.1 image render dễ scope creep.** Giữ 1 layout duy nhất, 1 colour scheme. Đừng làm "user chọn theme". Nếu render > 2s → cắt feature.

5. **C.2 + C.3 viết trước khi launch 1 tuần.** Operator cần đọc + suy ngẫm — không phải in ra trong ngày launch.

6. **C.4 founding member promise — document riêng.** Tạo `docs/current/founding-promise.md` ghi rõ commitment, expiry (none — lifetime), exception cases, owner. File này phải reference được từ Phase 5.7 detailed.

7. **Channel discipline — verify cứng `ZALO_CHANNEL_ENABLED=false`.** Trước khi launch, grep code base + check deploy config 2 lần. Không để vô tình activate Zalo bot và confuse cohort.

8. **Soft launch checkin daily 7 ngày đầu.** Operator + dev mỗi sáng đọc KPI digest cùng nhau 15 phút. Nhỏ nhưng tạo discipline. Đặc biệt chú ý in-onboarding emoji signal — đó là leading indicator của D7 retention.

9. **Acquisition distribution cẩn thận.** 50 invite link không phải 50 invite gửi cùng lúc. Distribute trong 3–5 ngày để operator support theo kịp. Founding member nhận hỗ trợ chất lượng cao = họ kể lại = viral grassroots.

10. **Operator self-care.** 50 user với SLA 24h feedback = ~3-5 feedback/ngày trong tuần đầu. Operator (= founder) phải block 1h/ngày cho việc này, không để tích lũy.
