# Phase 4.1 — Pre-Launch Hardening

> **Prerequisites:** Phase 4A (Financial Twin MVP) + Phase 4B (Twin Polish + Life Events + Cashflow v2 + Zalo OA adapter) shipped và stable trên main.
> **Thời gian:** ~3 tuần (mid-May → early-June 2026).
> **Mục tiêu:** Đưa Bé Tiền sang trạng thái **production-ready cho 50-user soft launch** vào tháng 6/2026 — không thêm "wow feature" mới, mà siết 3 trục: (1) first-session UX không lạc, (2) chi phí LLM không nổ, (3) feedback loop và observability đủ để học từ 50 user thật.
> **"Done":** 50 user thật onboard trong vòng 1 tuần đầu launch, D7 retention ≥ 40%, ≥ 70% user mở Twin trong session đầu, không có incident "LLM cost spike" hoặc "im lặng > 24h với feedback critical".

Phase 4.1 là **bản lề giữa "đã ship hết feature core" và "soft launch tháng 6"**. Phase 4A/4B đã làm Bé Tiền **đủ tính năng** — nhưng "đủ tính năng" không bằng "sẵn sàng cho 50 người lạ chạm vào lần đầu". Phase này tập trung vào 3 mối lo cụ thể:

1. **First impression rủi ro cao:** User mới mở bot không biết bắt đầu từ đâu → bounce trong 5 phút đầu → mất luôn cơ hội thấy Twin (wow-feature).
2. **Cost runaway nguy hiểm:** DeepSeek + Claude OCR + Whisper không có budget cap per user → 1 user spam OCR có thể đốt 10× budget tháng.
3. **Mù khi launch:** Không có Sentry, không có LLM dashboard, không có KPI digest → không biết user đang struggle ở đâu → fix chậm → mất user.

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

---

## 📅 Phân Bổ Thời Gian

| Tuần | Trọng tâm | Output chính |
|---|---|---|
| **Tuần 1 (~5 ngày)** | Epic A — Pre-launch hardening (phần 1): onboarding flow + cost guardrails | `/start` flow mới, budget cap middleware, daily cost report |
| **Tuần 2 (~5 ngày)** | Epic A — Pre-launch hardening (phần 2): observability + feedback triage | Sentry wired, LLM dashboard, KPI digest cron, feedback inbox UI |
| **Tuần 3 (~4 ngày)** | Epic B — Twin polish thực chiến + Epic C — Soft launch playbook | Shareable Twin image, predictions-vs-actual chart, 50-user playbook |

### Critical path

```
A.1 onboarding redesign ── A.2 first-Twin shortcut ── E2E first-session test
                                    │
A.3 cost guardrail middleware ── A.4 daily cost report
                                    │
A.5 Sentry + LLM dashboard ── A.6 KPI digest ── A.7 feedback triage UI
                                    │
B.1 shareable Twin image ── B.2 predictions-vs-actual ── ready
                                    │
C.1 acquisition source ── C.2 metrics rubric ── C.3 kill criteria ── launch
```

Critical path = A.1 → A.2 → A.5 → A.6 → C.2. Tất cả phải xong trước khi soft launch.

---

## 🗂️ Cấu Trúc Thay Đổi

### Files Touched

```
bot/handlers/
├── start_handler.py                          (rewrite: 3-step guided onboarding)
├── onboarding_handler.py                     (new: first-asset → first-Twin chain)
└── feedback_handler.py                       (extend: triage commands)

services/
├── onboarding/
│   └── onboarding_service.py                 (new: session state machine)
├── cost/
│   ├── budget_service.py                     (new: per-user budget cap logic)
│   └── cost_report_service.py                (new: daily aggregate)
├── twin/
│   ├── twin_share_service.py                 (new: shareable image generation)
│   └── twin_calibration_service.py           (new: predictions vs actual)
└── feedback/
    └── feedback_triage_service.py            (extend: SLA tracking)

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
└── feedback_sla_worker.py                    (new: alert if feedback unanswered > 24h)

scripts/
├── kpi_digest.py                             (new: standalone runnable)
├── soft_launch_acquisition.py                (new: invite link generator + tracking)
└── twin_calibration_backfill.py              (new: replay past Twin runs)

content/
├── onboarding/
│   ├── welcome_v2.yaml                       (new: 3-step guided strings)
│   └── first_twin_intro.yaml                 (new: "đây là Twin đầu tiên của bạn")
└── feedback/
    └── triage_responses.yaml                 (new: templated operator replies)

alembic/versions/
├── 4.1.01_user_cost_budgets.py               (new: per-user budget + spend tracking)
├── 4.1.02_feedback_sla_index.py              (new: index for SLA query)
└── 4.1.03_twin_calibration_log.py            (new: predicted vs actual snapshots)

docs/current/phase-4.1/
├── phase-4.1-detailed.md                     (this file)
├── phase-4.1-issues.md
├── phase-4.1-test-cases.md
└── phase-4.1-deploy-announcements.md
```

---

## 🗄️ Database Schema

### Migration `4.1.01_user_cost_budgets.py`

```sql
CREATE TABLE user_cost_budgets (
    user_id UUID PRIMARY KEY REFERENCES users(id),
    tier VARCHAR(16) NOT NULL DEFAULT 'free',          -- free | pro | cfo
    monthly_cap_vnd NUMERIC(15, 2) NOT NULL,            -- e.g. 30,000 VND for free
    current_month_spend_vnd NUMERIC(15, 2) NOT NULL DEFAULT 0,
    current_month_started_at DATE NOT NULL,
    last_warning_sent_at TIMESTAMPTZ NULL,              -- when 80%/100% warning was last delivered
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
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

**Lưu ý:** Budget cap mặc định **rộng tay** (30,000 VND/tháng cho free tier — đủ cho ~500 DeepSeek classify calls). Mục đích chính của bảng này KHÔNG phải monetize trong Phase 4.1 — mà là **stop the bleeding** nếu 1 user lỡ spam.

### Migration `4.1.02_feedback_sla_index.py`

```sql
CREATE INDEX idx_feedback_unanswered_age
    ON feedbacks(created_at)
    WHERE status = 'open';                              -- partial index for SLA query

ALTER TABLE feedbacks
    ADD COLUMN first_responded_at TIMESTAMPTZ NULL,
    ADD COLUMN sla_breach_alerted_at TIMESTAMPTZ NULL;
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

---

## 🔧 Epic A — Pre-Launch Hardening

**Goal:** Đưa onboarding, cost control, observability, và feedback triage lên mức production-grade. Đây là core của Phase 4.1 (~1.5 tuần).

**Stories:** A.1 → A.7 (7 stories)

### Story A.1 — Onboarding redesign (3-step guided flow)

**Layer:** `bot/handlers/start_handler.py` + `content/onboarding/welcome_v2.yaml`

**Acceptance:**
- `/start` lần đầu hiển thị message ngắn (< 200 chars) giới thiệu Bé Tiền + inline button "🌱 Bắt đầu hành trình".
- Sau khi bấm, dẫn user qua 3 bước rõ ràng: (1) chọn wealth level, (2) thêm asset đầu tiên (hỗ trợ skip với placeholder), (3) mở Twin đầu tiên.
- Mỗi bước có thanh tiến trình `(1/3)` `(2/3)` `(3/3)` ở đầu message.
- User có thể skip step 2 bằng nút "Để Bé Tiền dùng demo trước" → tạo 1 asset placeholder (50tr cash) để chạy Twin demo.
- Toàn bộ string nằm trong `welcome_v2.yaml`, không hardcode.

### Story A.2 — First-Twin shortcut

**Layer:** `services/onboarding/onboarding_service.py` + `bot/handlers/onboarding_handler.py`

**Acceptance:**
- Sau khi user hoàn tất step 2 (asset thật hoặc placeholder), service auto-trigger Twin computation và push kết quả qua message thứ 3 (không bắt user phải đi tìm menu).
- Time-to-first-Twin từ `/start` đến message hiển thị cone ≤ 5 phút (đo bằng `started_at` và `first_twin_shown_at` trong session log).
- Nếu Twin compute fail (e.g. DeepSeek timeout), fallback message giải thích "đang tính, bạn quay lại sau 1 phút nhé" — KHÔNG để user ngồi nhìn `...` 30s.
- Onboarding completion event log vào `intent_logs` với action `(onboarding, completed)`.

### Story A.3 — Cost guardrail middleware

**Layer:** `services/cost/budget_service.py` + `adapters/llm/cost_tracking_adapter.py` + `workers/cost_budget_worker.py`

**Acceptance:**
- Mọi LLM call đi qua `cost_tracking_adapter` wrap quanh DeepSeek/Claude/Whisper adapter hiện có.
- Trước mỗi call, service kiểm tra `user_cost_budgets.current_month_spend_vnd` < `monthly_cap_vnd`.
- Nếu đã chạm 80%: gửi message warning ấm áp cho user (1 lần/tháng), tiếp tục cho qua.
- Nếu chạm 100%: từ chối call, trả message "tháng này Bé Tiền tạm dừng tính năng X cho bạn, sang tháng mở lại" + suggest `/feedback` nếu user thật sự cần.
- Mỗi call success log vào `llm_cost_log` với provider/operation/tokens/cost/latency.
- Budget cap mặc định: free = 30,000 VND/tháng, pro = 150,000 VND/tháng, cfo = 400,000 VND/tháng. Tier hiện tại all = `free` (chưa có payment).

### Story A.4 — Daily cost report

**Layer:** `services/cost/cost_report_service.py` + `scripts/kpi_digest.py` (shared cron)

**Acceptance:**
- Mỗi sáng 8:00 ICT, operator nhận message Telegram tổng hợp 24h trước: tổng cost theo provider, top 5 user theo cost, user mới chạm 80% cap.
- Format ngắn (< 500 chars), số liệu round về 1k VND.
- Nếu tổng cost ngày > 200% trung bình 7 ngày trước → flag 🚨 ở đầu message.

### Story A.5 — Sentry + LLM metrics dashboard

**Layer:** `adapters/observability/sentry_adapter.py` + `adapters/observability/llm_metrics_adapter.py`

**Acceptance:**
- Sentry SDK wire vào FastAPI app + tất cả worker. Mọi unhandled exception capture với user_id + intent context.
- LLM metrics adapter ghi mỗi call: provider, operation, latency_ms, success/error, model_version. Export sang Prometheus hoặc đơn giản nhất: insert vào `llm_cost_log` (đã có Story A.3).
- Operator có dashboard (Grafana hoặc Metabase với connection trực tiếp PostgreSQL) hiển thị: error rate per intent, p50/p95 LLM latency, daily active users.
- ENV var `SENTRY_DSN` documented in `.env.example`, không hardcode.

### Story A.6 — Daily KPI digest cron

**Layer:** `workers/daily_kpi_digest_worker.py` + `scripts/kpi_digest.py`

**Acceptance:**
- Cron chạy 8:00 ICT mỗi sáng, gửi 1 message Telegram đến operator (user_id từ ENV `OPERATOR_TELEGRAM_ID`).
- Nội dung: DAU/WAU/MAU, số Twin view 24h, intent classification accuracy (% confirm vs % clarify), churn signals (user không active 7+ ngày), top 3 feedback chưa trả lời.
- Reuse cost report (Story A.4) vào cùng digest này — 1 message duy nhất buổi sáng.
- Nếu cron fail → Sentry alert (không silent).

### Story A.7 — Feedback triage UI

**Layer:** `bot/handlers/feedback_handler.py` (extend) + `services/feedback/feedback_triage_service.py` + `content/feedback/triage_responses.yaml`

**Acceptance:**
- Operator command `/feedback_inbox` liệt kê tất cả feedback `status=open` sắp xếp theo `created_at` cũ nhất trước.
- Mỗi feedback hiển thị: ID ngắn, user wealth level, snippet 100 chars, age ("2h trước", "1 ngày trước").
- Operator có thể reply bằng `/feedback_reply <id> <message>` — service gửi message đó cho user via Notifier, đánh dấu `first_responded_at = NOW()`, set `status = answered`.
- Có 5 template phản hồi nhanh trong `triage_responses.yaml` để operator dùng `/feedback_reply <id> --template thanks_logged`.
- Worker `feedback_sla_worker` chạy mỗi giờ: nếu có feedback `status=open` quá 24h → gửi alert đến operator (chỉ alert 1 lần per feedback).

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

### Story B.2 — Predictions vs actual

**Layer:** `services/twin/twin_calibration_service.py` + `scripts/twin_calibration_backfill.py`

**Acceptance:**
- Mỗi lần user mở Twin, service log snapshot vào `twin_calibration_snapshots` với 3 horizon: 7d, 30d, 90d.
- Worker chạy daily: với mỗi snapshot đến hạn, fill `actual_vnd` từ current net worth, compute `within_band`.
- Trong Twin view, thêm section "🎯 Bé Tiền đoán đúng bao nhiêu?" hiển thị % within-band của user (chỉ hiện khi có ≥ 3 snapshot completed).
- Honest framing: "Bé Tiền đoán đúng 7/9 lần (78%)" — KHÔNG inflate.
- Nếu hit-rate < 50%: hiển thị disclaimer "dự phóng chưa chuẩn, Bé Tiền đang học thêm" thay vì trốn số.

---

## 🔧 Epic C — Soft Launch Playbook

**Goal:** Operator có công cụ + tiêu chí rõ ràng để chạy 50-user soft launch.

**Stories:** C.1 → C.3 (3 stories, ~3-5 ngày)

### Story C.1 — Acquisition source + invite tracking

**Layer:** `scripts/soft_launch_acquisition.py` + `bot/handlers/start_handler.py` (extend)

**Acceptance:**
- Script generate 50 unique invite link `t.me/BeTienBot?start=invite_<token>` với metadata (source, batch_name) lưu vào table `invite_codes`.
- Khi user mới start bot với token, log source vào `users.acquisition_source`.
- Operator có command `/cohort_stats` xem breakdown user theo source.
- Source ban đầu: `friends`, `personal_fb`, `vn_finance_community`, `direct_msg`.

### Story C.2 — Success metrics rubric

**Layer:** Documentation only — không code mới. Output: `docs/current/phase-4.1/success-metrics.md`.

**Acceptance:**
- Document 6 metric với target + measurement method + cron để compute:
  - D1 retention ≥ 70%
  - D7 retention ≥ 40%
  - % user mở Twin trong session đầu ≥ 70%
  - % user log ≥ 1 asset thật trong 7 ngày đầu ≥ 60%
  - Intent classification accuracy ≥ 85%
  - Feedback SLA (response < 24h) ≥ 95%
- Mỗi metric link đến SQL query để compute từ existing tables.

### Story C.3 — Kill criteria

**Layer:** Documentation only — output: `docs/current/phase-4.1/kill-criteria.md`.

**Acceptance:**
- Document tiêu chí dừng/pivot rõ ràng:
  - 4-week retention < 20% → pivot positioning hoặc kill product
  - Cost per active user > 50k VND/tháng sau 1 tháng → re-evaluate LLM budget
  - Critical bug rate (Sentry P1) > 1/day với cohort 50 user → freeze feature, fix sprint
  - Bé Tiền persona violation reported > 5 lần/tuần → prompt audit toàn bộ
- Mỗi tiêu chí có owner (operator/PM), threshold rõ ràng, action plan.

---

## 📐 Layer Mapping & Contract Compliance

| Story | Routers | Workers | Handlers | Services | Adapters |
|---|---|---|---|---|---|
| A.1 onboarding | — | — | `start_handler`, `onboarding_handler` | `onboarding_service` | Notifier (existing) |
| A.2 first-Twin | — | — | `onboarding_handler` | `onboarding_service` → `twin_engine_service` | Notifier |
| A.3 cost guardrail | — | `cost_budget_worker` | — (middleware) | `budget_service` | `cost_tracking_adapter` wraps DeepSeek/Claude/Whisper |
| A.4 daily cost report | — | `daily_kpi_digest_worker` | — | `cost_report_service` | Notifier |
| A.5 Sentry | (init) | (init) | — | — | `sentry_adapter`, `llm_metrics_adapter` |
| A.6 KPI digest | — | `daily_kpi_digest_worker` | — | (composes existing services) | Notifier |
| A.7 feedback triage | — | `feedback_sla_worker` | `feedback_handler` (extend) | `feedback_triage_service` | Notifier |
| B.1 share image | — | — | (button on existing Twin view) | `twin_share_service` | `twin_image_renderer` (PIL) |
| B.2 calibration | — | `twin_calibration_worker` | — | `twin_calibration_service` | — |
| C.1 invite tracking | — | — | `start_handler` (extend) | — | — |

**Contract checks:**
- `cost_tracking_adapter` chặn LLM call → phải raise domain exception (e.g. `BudgetExceededError`), service xử lý + return user-facing message qua content yaml. KHÔNG để adapter gọi Telegram trực tiếp.
- `budget_service` chỉ `flush`, không `commit`. Worker `cost_budget_worker` commit tại boundary.
- Sentry init phải xảy ra trước khi router/worker dispatch — đặt trong `main.py` lifecycle hook.
- Toàn bộ Vietnamese string trong content/*.yaml — check bằng `vi-localization-checker` agent trước merge.

---

## ⚠️ Risk & Rollback

| Risk | Severity | Mitigation | Rollback |
|---|---|---|---|
| Onboarding mới làm rối user cũ | Medium | Detect `users.created_at < phase_4_1_deploy_date` → vẫn dùng flow cũ; chỉ user mới mới qua `welcome_v2` | Feature flag `ONBOARDING_V2_ENABLED` env, set false |
| Budget cap chặn nhầm user đang dùng nhiều legit | High | Default cap rộng tay; operator command `/budget_set <user> <amount>` để bump 1-1; warning 80% trước khi block | Bypass cho all = set `monthly_cap_vnd = 999999` qua SQL |
| Sentry leak PII (user message, money) | High | Beforesend hook scrub: regex strip số > 6 digit, strip email/phone; whitelist field thay vì blacklist | Disable Sentry qua env `SENTRY_DSN=""` |
| Shareable image làm leak privacy (user share thật) | Medium | Không hiện số tuyệt đối + watermark + user phải tự bấm save (không auto-share) | Disable button qua feature flag |
| Calibration honest framing demotivate user | Low | Chỉ hiện khi ≥ 3 snapshot, ngôn ngữ "Bé Tiền đang học" thay vì "Bé Tiền đoán sai" | Hide section qua feature flag, vẫn log snapshot |
| KPI digest spam operator | Low | Throttle: 1 message/ngày max, gộp tất cả info | Disable cron |

---

## ✅ Definition of Done

- [ ] Tất cả Story A.1–A.7, B.1–B.2, C.1–C.3 acceptance criteria pass.
- [ ] Migration `4.1.01`, `4.1.02`, `4.1.03` applied trên dev + staging.
- [ ] Test cases `phase-4.1-test-cases.md` pass với 5 persona; signoff marker = `signed`.
- [ ] `vi-localization-checker` agent pass — không có hardcoded Vietnamese string trong code.
- [ ] `layer-contract-checker` agent pass — service không có `db.commit()`, adapter không có business logic.
- [ ] Sentry capture ít nhất 1 test exception trong staging.
- [ ] KPI digest đã chạy 3 ngày liên tiếp trên staging với data thật.
- [ ] Operator đã test flow: `/feedback_inbox` → `/feedback_reply` → user nhận message.
- [ ] Cost report cho ngày test có ≥ 1 LLM call → cost > 0 → log đầy đủ.
- [ ] First-session test: clean account → `/start` → < 5 phút thấy Twin (đo trên staging).
- [ ] `success-metrics.md` + `kill-criteria.md` đã commit.
- [ ] 50 invite link đã generate, lưu vào DB, in CSV cho operator distribute.
- [ ] Deploy announcement teaser/launch/followup đã preview qua `--dry-run` với operator account.

---

## 🚧 Out of Scope

Phase 4.1 cố tình **không** làm những việc sau (defer hoặc đã có phase riêng):

- ❌ Pricing re-validation hoặc payment integration → Phase 5.7 (Monetization Infra)
- ❌ Zalo channel rollout → Phase 5.1/5.2/5.3
- ❌ Achievement/badge system → Phase 5.4
- ❌ Life event simulator polish nâng cao → đã ship trong 4B, không touch lại
- ❌ Multi-tier user (free/pro/cfo) UI/flow → table có sẵn (`user_cost_budgets.tier`), tier hiện tại all = `free`, chuyển tier qua SQL khi cần test
- ❌ Notion dashboard upgrade → giữ nguyên Phase 3A
- ❌ Tính năng "social" (leaderboard, friend share) → Vietnamese cultural fit nói KHÔNG
- ❌ Refactor lớn services/twin/ — Phase 4A vừa ship, chỉ thêm, không sửa

---

## 🧭 Recommendations

1. **Tuần 1 dồn force lên A.1 + A.2.** Onboarding là phần dễ trượt timeline nhất vì cần dogfood nhiều lần. Mỗi developer commit thử `/start` từ clean account ít nhất 1 lần/ngày.

2. **A.3 cost guardrail viết test trước.** Đây là middleware đụng tất cả LLM call — bug ở đây = LLM call fail toàn bộ. Viết integration test với mock DeepSeek + mock budget trước khi wire production.

3. **A.5 Sentry — đừng để cuối cùng.** Wire Sentry ngay tuần 1 (1-2h work). Mọi bug fix sau đó sẽ có stack trace tốt hơn → tiết kiệm thời gian dogfood.

4. **B.1 image render dễ scope creep.** Giữ 1 layout duy nhất, 1 colour scheme. Đừng làm "user chọn theme". Nếu render > 2s → cắt feature.

5. **C.2 + C.3 viết trước khi launch 1 tuần.** Operator cần đọc + suy ngẫm — không phải in ra trong ngày launch.

6. **Soft launch checkin daily 7 ngày đầu.** Operator + dev mỗi sáng đọc KPI digest cùng nhau 15 phút. Nhỏ nhưng tạo discipline.
