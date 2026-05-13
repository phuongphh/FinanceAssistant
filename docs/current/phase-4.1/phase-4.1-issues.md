# Phase 4.1 — GitHub Issues

> File này là source-of-truth để OpenClaw PM Agent generate GitHub Issues qua Actions sync.
> Format: Epic-as-parent / Story-as-child. Mỗi Story có parent epic reference.
> Labels chuẩn: `phase-4.1`, `epic-{a|b|c}`, `story`, `epic`, plus area labels (`area-onboarding`, `area-cost`, `area-observability`, etc.)

---

## EPIC #1: Pre-Launch Hardening

**Type:** Epic
**Labels:** `phase-4.1`, `epic-a`, `epic`, `priority-p0`
**Estimate:** ~1.5 tuần (8 stories)
**Owner:** TBD

### Description

Đưa onboarding, cost control, observability, feedback triage, và first-briefing experience lên mức production-grade trước soft launch 50-user. Đây là core của Phase 4.1.

### Goals

- First 5 phút từ `/start` → user thấy Twin của chính mình
- Không có cost runaway: budget cap per user enforce trước mọi LLM call
- Sentry + KPI digest chạy daily từ ngày 1
- Feedback SLA < 24h, có công cụ triage cho operator
- First morning briefing có frame riêng, không assume user biết đọc

### Child Stories

- #A.1 Onboarding redesign (3-step goal-based flow)
- #A.2 First-Twin shortcut + narrative + in-moment feedback
- #A.3 Cost guardrail middleware
- #A.4 Daily cost report
- #A.5 Sentry + LLM metrics dashboard
- #A.6 Daily KPI digest cron
- #A.7 Feedback triage UI
- #A.8 First morning briefing onboarding

### Definition of Done

- All 8 child stories acceptance criteria pass
- E2E test: clean account → `/start` → < 5 phút thấy Twin (đo trên staging)
- Sentry capture test exception verified với PII scrub
- KPI digest đã chạy 3 ngày liên tiếp trên staging

---

## STORY #A.1: Onboarding redesign (3-step goal-based flow)

**Type:** Story
**Parent:** EPIC #1 (Pre-Launch Hardening)
**Labels:** `phase-4.1`, `epic-a`, `story`, `area-onboarding`, `priority-p0`
**Estimate:** 2 ngày

### Description

Rewrite `/start` flow thành 3-step guided onboarding. Step 1 hỏi mục tiêu (không phải wealth level — culture-risk với VN mass affluent). Step 2 nhập asset đầu hoặc dùng demo (với framing rõ ràng). Step 3 auto-trigger Twin (xem A.2).

### Layer

- `bot/handlers/start_handler.py` (rewrite)
- `content/onboarding/welcome_v2.yaml` (new)
- `content/onboarding/demo_mode_framing.yaml` (new)
- `services/onboarding/onboarding_service.py` (new)
- `services/onboarding/wealth_inference_service.py` (new)

### Acceptance Criteria

- [ ] `/start` lần đầu hiển thị message < 200 chars + inline button "🌱 Bắt đầu hành trình"
- [ ] Mỗi step có thanh tiến trình `(1/3)` `(2/3)` `(3/3)` ở đầu message
- [ ] **Step 1 — Goal question** với 3 inline button: 🌱 Hiểu rõ tổng tài sản / 🎯 Lên kế hoạch mục tiêu lớn / 📊 Theo dõi chi tiêu thông minh → lưu vào `onboarding_sessions.goal_choice`
- [ ] **Step 2 — First asset:** prompt nhập số tiền VND (free text) hoặc skip qua "Để Bé Tiền dùng demo trước"
- [ ] **Demo mode banner** khi skip: *"📌 Demo Mode — đây là Twin của một người giả định với 50tr tiết kiệm. Twin của bạn sẽ khác — nhập tài sản thật để xem Twin riêng của bạn."* + CTA "💎 Xem Twin của tôi" để quay lại Step 2
- [ ] **Wealth segment inference** từ asset value:
  - < 100tr → `starter`
  - 100tr–500tr → `young_pro`
  - 500tr–5 tỷ → `mass_affluent`
  - > 5 tỷ → `hnw`
  - Lưu vào `onboarding_sessions.inferred_wealth_segment`
- [ ] **Source-aware welcome copy** từ `users.acquisition_source` (mapping `friends`/`personal_fb`/`vn_finance_community`/`tg_finance_groups`/`direct_msg` trong yaml)
- [ ] Toàn bộ Vietnamese strings trong `welcome_v2.yaml`, không hardcode
- [ ] `vi-localization-checker` agent pass

### Technical Notes

- `wealth_inference_service` là pure function (no DB write) — called by `onboarding_service`
- State machine có 4 state: `goal_question` → `first_asset` → `twin_shown` → `completed`
- User có thể quay lại sửa: nếu user gõ `/start` lại khi `current_step != 'completed'`, hỏi resume hay restart

### Dependencies

- Blocks: #A.2 (depends on session state from A.1)
- Depends on: Migration `4.1.04` (onboarding_sessions table)

---

## STORY #A.2: First-Twin shortcut + narrative + in-moment feedback

**Type:** Story
**Parent:** EPIC #1
**Labels:** `phase-4.1`, `epic-a`, `story`, `area-onboarding`, `area-twin`, `priority-p0`
**Estimate:** 2 ngày

### Description

Sau Step 2, auto-trigger Twin computation và push 3 message liên tiếp: (1) mascot narrative, (2) cone chart, (3) in-moment feedback prompt. Implement resume worker cho user dừng giữa onboarding.

### Layer

- `services/onboarding/onboarding_service.py` (extend)
- `services/twin/twin_narrative_service.py` (new)
- `bot/handlers/onboarding_handler.py` (new)
- `workers/onboarding_resume_worker.py` (new)
- `content/onboarding/first_twin_intro.yaml` (new)
- `content/onboarding/resume_nudge.yaml` (new)

### Acceptance Criteria

- [ ] Sau Step 2, service auto-trigger `twin_engine_service.compute()` cho user
- [ ] Push 3 message liên tiếp:
  - [ ] (1) **Mascot narrative** từ `first_twin_intro.yaml`: *"Đây là Twin tài chính của bạn — Bé Tiền vẽ ra 3 con đường tương lai..."*
  - [ ] (2) **Cone chart image** (gọi existing twin engine render)
  - [ ] (3) Sau delay 5–10s, **feedback prompt**: *"💬 Bạn cảm thấy thế nào về Twin đầu tiên?"* với 3 inline button 😍 / 🤔 / 😕
- [ ] Feedback bấm vào:
  - [ ] Lưu signal vào `onboarding_sessions.onboarding_feedback_signal`
  - [ ] Tạo record trong `feedbacks` với `onboarding_emoji_signal` = giá trị emoji
  - [ ] Acknowledge: *"Cảm ơn bạn — Bé Tiền ghi nhận để cải thiện"*
- [ ] **TTFT đo được**: `first_twin_shown_at - started_at` < 5 phút trong staging E2E test
- [ ] **Fallback nếu Twin compute fail**: message *"Bé Tiền đang tính, bạn quay lại sau 1 phút nhé"* — KHÔNG `...` 30s
- [ ] **Resume worker `onboarding_resume_worker`**:
  - [ ] Chạy mỗi 5 phút
  - [ ] Query `onboarding_sessions` WHERE `current_step != 'completed'` AND `nudge_sent_at IS NULL` AND `updated_at < NOW() - 10 minutes`
  - [ ] Gửi **1 message duy nhất** với 2 button "Tiếp tục" / "Để Bé Tiền dùng demo trước"
  - [ ] Set `nudge_sent_at = NOW()` để không gửi lần 2 (cap vĩnh viễn)
- [ ] Onboarding completion log vào `intent_logs` với action `(onboarding, completed)` và metadata `{goal, segment}`

### Technical Notes

- `twin_narrative_service` là composer pattern — không gọi LLM, chỉ format yaml + inject user values
- Feedback prompt timing dùng `asyncio.sleep(7)` — không block handler
- Worker contract: chỉ flush trong service, commit trong worker boundary

### Dependencies

- Blocks: #A.8 (first briefing depends on onboarding completed)
- Depends on: #A.1

---

## STORY #A.3: Cost guardrail middleware

**Type:** Story
**Parent:** EPIC #1
**Labels:** `phase-4.1`, `epic-a`, `story`, `area-cost`, `priority-p0`
**Estimate:** 2 ngày

### Description

Wrap tất cả LLM call (DeepSeek/Claude/Whisper) qua cost-tracking adapter. Enforce per-user monthly budget cap. Warning ở 80%, block ở 100%.

### Layer

- `services/cost/budget_service.py` (new)
- `adapters/llm/cost_tracking_adapter.py` (new)
- `workers/cost_budget_worker.py` (new)
- `content/cost/budget_messages.yaml` (new)

### Acceptance Criteria

- [ ] Mọi LLM call đi qua `cost_tracking_adapter` wrap quanh DeepSeek/Claude/Whisper
- [ ] Trước mỗi call:
  - [ ] Check `current_month_spend_vnd < monthly_cap_vnd`
  - [ ] Nếu đã chạm 80%: gửi warning ấm áp (1 lần/tháng, lưu `last_warning_sent_at`), tiếp tục cho qua
  - [ ] Nếu chạm 100%: raise `BudgetExceededError`, không gọi LLM
- [ ] Sau mỗi call success: insert vào `llm_cost_log` (provider/operation/tokens/cost/latency)
- [ ] **Budget cap default**: free = 30,000 VND/tháng, pro = 100,000 VND/tháng (chưa active v1)
- [ ] **Constraint check** `chk_tier_v1` từ migration `4.1.01` enforce `tier IN ('free', 'pro')`
- [ ] Operator command `/budget_set <user_id> <amount>` để override per-user
- [ ] Service raise domain exception `BudgetExceededError` — adapter KHÔNG gọi Telegram trực tiếp
- [ ] `budget_service` chỉ flush, không commit; worker commit tại boundary
- [ ] Integration test với mock DeepSeek + mock budget pass

### Technical Notes

- Cost computation: tokens_in × in_price + tokens_out × out_price (per provider), exchange rate VND/USD lấy từ ENV (`USD_VND_RATE`, default 25000)
- Whisper cost = duration_seconds × rate
- Claude OCR cost = page count × rate

### Dependencies

- Blocks: #A.4, #A.5 (cost data feeds dashboard)
- Depends on: Migration `4.1.01`

---

## STORY #A.4: Daily cost report

**Type:** Story
**Parent:** EPIC #1
**Labels:** `phase-4.1`, `epic-a`, `story`, `area-cost`, `area-observability`, `priority-p1`
**Estimate:** 0.5 ngày

### Description

Mỗi sáng 8h, operator nhận message tổng hợp cost 24h. Merge vào KPI digest (#A.6) để chỉ có 1 message/sáng.

### Layer

- `services/cost/cost_report_service.py` (new)
- `scripts/kpi_digest.py` (shared with A.6)

### Acceptance Criteria

- [ ] Function `cost_report_service.daily_summary(date)` trả về object với:
  - [ ] Tổng cost theo provider (DeepSeek / Claude / Whisper)
  - [ ] Top 5 user theo cost với user_id snippet
  - [ ] User mới chạm 80% cap trong ngày
- [ ] Format < 500 chars, số liệu round về 1k VND
- [ ] Flag 🚨 đầu message nếu tổng cost > 200% trung bình 7 ngày trước
- [ ] Output được consume bởi `daily_kpi_digest_worker` (#A.6), KHÔNG gửi message riêng

### Dependencies

- Depends on: #A.3 (cost data)
- Merged into: #A.6

---

## STORY #A.5: Sentry + LLM metrics dashboard

**Type:** Story
**Parent:** EPIC #1
**Labels:** `phase-4.1`, `epic-a`, `story`, `area-observability`, `priority-p0`
**Estimate:** 1 ngày

### Description

Wire Sentry vào FastAPI + workers. Build Metabase dashboard cho LLM metrics. PII scrub strict trước khi send Sentry.

### Layer

- `adapters/observability/sentry_adapter.py` (new)
- `adapters/observability/llm_metrics_adapter.py` (new)
- `main.py` (init Sentry trong lifecycle hook)

### Acceptance Criteria

- [ ] Sentry SDK wire vào FastAPI app + tất cả worker process
- [ ] Mọi unhandled exception capture với user_id (hash, không plain) + intent context
- [ ] **PII scrub trong beforesend hook**:
  - [ ] Strip số > 6 digits (tiền)
  - [ ] Strip email regex
  - [ ] Strip phone regex (+84..., 0...)
  - [ ] **Whitelist** field thay vì blacklist: chỉ pass `intent_type`, `step`, `error_message_template_id`, `user_id_hash`
- [ ] Test exception trong staging → verify Sentry nhận với PII đã scrub
- [ ] LLM metrics adapter ghi mỗi call vào `llm_cost_log`: provider, operation, latency_ms, success/error, model_version
- [ ] Metabase dashboard với connection trực tiếp PostgreSQL hiển thị:
  - [ ] Error rate per intent (24h, 7d)
  - [ ] p50/p95 LLM latency per provider
  - [ ] Daily active users
- [ ] ENV `SENTRY_DSN` documented trong `.env.example`, không hardcode
- [ ] Sentry init phải trước router/worker dispatch

### Dependencies

- Blocks: nothing (foundational)
- Recommendation: ship tuần 1 để stack trace tốt cho mọi bug fix sau

---

## STORY #A.6: Daily KPI digest cron

**Type:** Story
**Parent:** EPIC #1
**Labels:** `phase-4.1`, `epic-a`, `story`, `area-observability`, `priority-p0`
**Estimate:** 1 ngày

### Description

Cron 8h sáng gửi **1 message duy nhất** Telegram đến operator gộp cost report + engagement KPI + feedback queue.

### Layer

- `workers/daily_kpi_digest_worker.py` (new)
- `scripts/kpi_digest.py` (new, standalone runnable)

### Acceptance Criteria

- [ ] Cron schedule 8:00 ICT mỗi sáng
- [ ] Gửi đến `OPERATOR_TELEGRAM_ID` từ ENV
- [ ] Nội dung gộp:
  - [ ] **Cost section** (từ #A.4): tổng cost 24h, top 5 user, user chạm 80%
  - [ ] **Engagement section**: DAU/WAU/MAU, số Twin view 24h, số onboarding completed
  - [ ] **Quality section**: Intent classification accuracy (% confirm vs % clarify), in-onboarding emoji breakdown (😍/🤔/😕)
  - [ ] **Churn signals**: User không active 7+ ngày (gồm founding members nếu có)
  - [ ] **Feedback queue**: Top 3 feedback chưa trả lời với age
- [ ] Format Telegram message < 4000 chars (giới hạn Telegram)
- [ ] Nếu cron fail → Sentry alert
- [ ] Standalone script `python scripts/kpi_digest.py --date 2026-05-15` chạy được không qua cron

### Dependencies

- Depends on: #A.3, #A.4, #A.5

---

## STORY #A.7: Feedback triage UI

**Type:** Story
**Parent:** EPIC #1
**Labels:** `phase-4.1`, `epic-a`, `story`, `area-feedback`, `priority-p0`
**Estimate:** 1 ngày

### Description

Operator commands để đọc inbox, reply nhanh với templates, SLA alert nếu feedback > 24h chưa trả lời.

### Layer

- `bot/handlers/feedback_handler.py` (extend)
- `services/feedback/feedback_triage_service.py` (new)
- `workers/feedback_sla_worker.py` (new)
- `content/feedback/triage_responses.yaml` (new)

### Acceptance Criteria

- [ ] **`/feedback_inbox`** liệt kê tất cả `status=open` sắp theo `created_at` cũ nhất trước
- [ ] Mỗi feedback hiển thị: ID ngắn (8 chars), user wealth_segment, **founding flag (🌱)** nếu có, snippet 100 chars, age ("2h trước"), **in-onboarding emoji signal** nếu có
- [ ] **`/feedback_reply <id> <message>`**:
  - [ ] Gửi message cho user via Notifier
  - [ ] Đánh dấu `first_responded_at = NOW()`
  - [ ] Set `status = answered`
- [ ] **5 templates** trong `triage_responses.yaml`:
  - [ ] `thanks_logged` — *"Cảm ơn bạn — Bé Tiền đã ghi nhận và đang xem qua."*
  - [ ] `clarify_request` — *"Bạn cho Bé Tiền biết thêm về [X] được không?"*
  - [ ] `feature_acknowledged` — *"Ý tưởng hay — Bé Tiền lưu vào roadmap."*
  - [ ] `bug_apology` — *"Xin lỗi bạn, đây là bug đang fix — kết quả sẽ có trong 24h."*
  - [ ] `not_supported_yet` — *"Tính năng này chưa có nhưng đang trong kế hoạch — Bé Tiền sẽ báo khi sẵn sàng."*
- [ ] **`/feedback_reply <id> --template thanks_logged`** dùng template
- [ ] **`feedback_sla_worker`** chạy mỗi giờ:
  - [ ] Query feedback `status=open` AND `created_at < NOW() - 24h` AND `sla_breach_alerted_at IS NULL`
  - [ ] Alert operator (1 lần per feedback), set `sla_breach_alerted_at`

### Dependencies

- Depends on: Migration `4.1.02` (feedback_sla_index + columns)

---

## STORY #A.8: First morning briefing onboarding

**Type:** Story
**Parent:** EPIC #1
**Labels:** `phase-4.1`, `epic-a`, `story`, `area-briefing`, `area-onboarding`, `priority-p1`
**Estimate:** 1 ngày

### Description

First briefing có format khác briefing thường — có explainer ngắn và button "Bé Tiền đang nói gì?". Logic đơn giản: gửi 8h sáng ngày sau onboarding bất kể.

### Layer

- `services/briefing/first_briefing_service.py` (new)
- `content/onboarding/first_briefing.yaml` (new)
- Existing briefing worker (extend với branch on `is_first_briefing`)

### Acceptance Criteria

- [ ] Service detect first briefing bằng query `briefing_logs` đếm count cho user_id — nếu = 0 trước briefing này thì áp first-briefing format
- [ ] First briefing format:
  - [ ] Mở đầu: *"Đây là briefing đầu tiên của bạn! Mỗi sáng 8h Bé Tiền sẽ tổng hợp 3 thứ quan trọng nhất về tài sản của bạn trong 30 giây đọc. Hôm nay Bé Tiền nói về:"*
  - [ ] 3 mục briefing thường
  - [ ] Inline button "💡 Bé Tiền đang nói gì?" → hiện explanation chi tiết từng metric (text trong yaml)
- [ ] **Timing đơn giản**: gửi 8h sáng **ngày sau onboarding**, không apply smart logic. Nếu user mute notification, briefing vẫn nằm trong chat khi mở lại.
- [ ] Log event vào `intent_logs` với action `(briefing, first_shown)`
- [ ] Toàn bộ string trong `first_briefing.yaml`

### Dependencies

- Depends on: #A.1, #A.2 (onboarding completed event)

---

## EPIC #2: Twin Polish Thực Chiến

**Type:** Epic
**Labels:** `phase-4.1`, `epic-b`, `epic`, `priority-p1`
**Estimate:** ~1 tuần (2 stories)

### Description

Lấy 2 user request lớn nhất từ Phase 4A dogfood — *"muốn share Twin"* và *"Twin đoán có đúng không?"* — để build trust trước launch.

### Child Stories

- #B.1 Shareable Twin image
- #B.2 Predictions vs actual

---

## STORY #B.1: Shareable Twin image

**Type:** Story
**Parent:** EPIC #2
**Labels:** `phase-4.1`, `epic-b`, `story`, `area-twin`, `priority-p1`
**Estimate:** 2 ngày

### Description

Nút "📸 Lưu thành ảnh" trên Twin view → render PNG với cone chart + summary. KHÔNG hiển thị số tiền tuyệt đối (privacy). Có founding badge nếu user là founding member.

### Layer

- `services/twin/twin_share_service.py` (new)
- `adapters/image/twin_image_renderer.py` (new, dùng PIL/Pillow)

### Acceptance Criteria

- [ ] Trong Twin view (Telegram), thêm nút "📸 Lưu thành ảnh"
- [ ] Bấm → trả về PNG render
- [ ] Image chứa: % tăng trưởng, time horizon, watermark "Bé Tiền — Personal CFO". **KHÔNG** chứa số tiền tuyệt đối.
- [ ] Render < 1s (PIL/Pillow, không headless browser)
- [ ] Background gradient + Bé Tiền mascot góc dưới phải
- [ ] **Founding badge** "🌱 Founding Member" góc trên trái nếu `users.is_founding_member = TRUE`
- [ ] User save về máy hoặc share — Bé Tiền KHÔNG chủ động prompt share FB/Zalo
- [ ] Feature flag `TWIN_SHARE_ENABLED` (default ON, rollback nếu cần)

### Dependencies

- Depends on: existing Twin view from Phase 4A

---

## STORY #B.2: Predictions vs actual

**Type:** Story
**Parent:** EPIC #2
**Labels:** `phase-4.1`, `epic-b`, `story`, `area-twin`, `priority-p1`
**Estimate:** 2 ngày

### Description

Log Twin snapshot mỗi lần user mở, fill actual sau 7/30/90 ngày, hiển thị hit-rate honest framing.

### Layer

- `services/twin/twin_calibration_service.py` (new)
- `workers/twin_calibration_worker.py` (new)
- `scripts/twin_calibration_backfill.py` (new)

### Acceptance Criteria

- [ ] Mỗi lần user mở Twin → log snapshot vào `twin_calibration_snapshots` với 3 horizon: 7d, 30d, 90d
- [ ] Worker daily: query snapshot due (predicted_at + horizon_days < NOW), fill `actual_vnd` từ current net worth, compute `within_band` (P10 ≤ actual ≤ P90)
- [ ] Trong Twin view, thêm section "🎯 Bé Tiền đoán đúng bao nhiêu?":
  - [ ] Chỉ hiện khi user có ≥ 3 snapshot completed
  - [ ] Honest framing: *"Bé Tiền đoán đúng 7/9 lần (78%)"* — KHÔNG inflate
  - [ ] Nếu hit-rate < 50%: hiển thị *"Dự phóng chưa chuẩn, Bé Tiền đang học thêm"*
- [ ] Backfill script `twin_calibration_backfill.py` cho dogfood data từ Phase 4A
- [ ] Feature flag `TWIN_CALIBRATION_DISPLAY_ENABLED` (mặc định ON, rollback ẩn section nhưng vẫn log snapshot)

### Dependencies

- Depends on: Migration `4.1.03`

---

## EPIC #3: Soft Launch Playbook & Founding Cohort

**Type:** Epic
**Labels:** `phase-4.1`, `epic-c`, `epic`, `priority-p0`
**Estimate:** ~5 ngày (4 stories)

### Description

Operator có công cụ + tiêu chí rõ ràng để chạy 50-user soft launch trên Telegram. Founding member scaffolding cho promise 50% lifetime discount.

### Child Stories

- #C.1 Acquisition source + invite tracking + source-aware copy
- #C.2 Success metrics rubric (doc only)
- #C.3 Kill criteria (doc only)
- #C.4 Founding member experience

---

## STORY #C.1: Acquisition source + invite tracking + source-aware copy

**Type:** Story
**Parent:** EPIC #3
**Labels:** `phase-4.1`, `epic-c`, `story`, `area-acquisition`, `priority-p0`
**Estimate:** 1 ngày

### Description

Generate 50 invite link, track source, source-aware welcome copy.

### Layer

- `scripts/soft_launch_acquisition.py` (new)
- `bot/handlers/start_handler.py` (extend)
- `content/onboarding/welcome_v2.yaml` (source variant)

### Acceptance Criteria

- [ ] Script generate **exactly 50** invite link `t.me/BeTienBot?start=invite_<token>` với:
  - [ ] Metadata: `source`, `batch_name`, `grants_founding_status=TRUE`
  - [ ] Lưu vào `invite_codes` table
- [ ] Khi user redeem invite:
  - [ ] Log `source` vào `users.acquisition_source`
  - [ ] Nếu `grants_founding_status=TRUE` → mark user là founding (#C.4 logic)
- [ ] **`/cohort_stats`** operator command: breakdown user theo source
- [ ] 5 source values: `friends`, `personal_fb`, `vn_finance_community`, `direct_msg`, `tg_finance_groups`
- [ ] **Source-aware copy** trong `welcome_v2.yaml`:
  - [ ] `friends` / `personal_fb` → warm tone với placeholder `{referrer_name}`
  - [ ] `vn_finance_community` / `tg_finance_groups` → professional tone
  - [ ] `direct_msg` → personal tone
- [ ] CSV output: 50 dòng với `invite_url`, `source`, `batch_name`

### Dependencies

- Depends on: Migration `4.1.04`

---

## STORY #C.2: Success metrics rubric (doc only)

**Type:** Story
**Parent:** EPIC #3
**Labels:** `phase-4.1`, `epic-c`, `story`, `area-metrics`, `docs-only`, `priority-p0`
**Estimate:** 0.5 ngày

### Description

Document 8 metric với target + measurement method + SQL query.

### Output

`docs/current/phase-4.1/success-metrics.md`

### Acceptance Criteria

- [ ] Document 8 metric:
  - [ ] **D1 retention ≥ 70%** — % founding member quay lại ngày 2
  - [ ] **D7 retention ≥ 40%** — % founding member active tuần 2
  - [ ] **% user mở Twin trong session đầu ≥ 70%** — `onboarding_sessions.first_twin_shown_at IS NOT NULL`
  - [ ] **% user log ≥ 1 asset thật trong 7 ngày đầu ≥ 60%** — `assets` table, exclude placeholder
  - [ ] **Intent classification accuracy ≥ 85%** — `intent_logs` (% confirmed vs clarified vs misexecuted)
  - [ ] **Feedback SLA < 24h ≥ 95%** — `feedbacks.first_responded_at - created_at`
  - [ ] **In-onboarding emoji signal**: % 😍 ≥ 50%
  - [ ] **Twin satisfaction sau D7**: qualitative interview với 10 founding member ngẫu nhiên
- [ ] Mỗi metric có SQL query để compute từ existing tables
- [ ] Mỗi metric có cron schedule để monitor

### Dependencies

- Depends on: schema từ A.1–A.8

---

## STORY #C.3: Kill criteria (doc only)

**Type:** Story
**Parent:** EPIC #3
**Labels:** `phase-4.1`, `epic-c`, `story`, `area-metrics`, `docs-only`, `priority-p0`
**Estimate:** 0.5 ngày

### Description

Document tiêu chí dừng/pivot.

### Output

`docs/current/phase-4.1/kill-criteria.md`

### Acceptance Criteria

- [ ] Document 6 tiêu chí với owner + threshold + action plan:
  - [ ] **4-week retention < 20%** → pivot positioning hoặc kill product
  - [ ] **Cost per active user > 50k VND/tháng** sau 1 tháng → re-evaluate LLM budget hoặc model choice
  - [ ] **Critical bug rate (Sentry P1) > 1/day** với cohort 50 user → freeze feature, fix sprint
  - [ ] **Bé Tiền persona violation reported > 5 lần/tuần** → prompt audit toàn bộ
  - [ ] **In-onboarding emoji signal 😕 > 30%** → first-impression broken, redesign A.1+A.2
  - [ ] **Twin within-band hit rate < 40%** sau 90 ngày → calibration model rework

### Dependencies

- None

---

## STORY #C.4: Founding member experience

**Type:** Story
**Parent:** EPIC #3
**Labels:** `phase-4.1`, `epic-c`, `story`, `area-acquisition`, `area-monetization`, `priority-p0`
**Estimate:** 1 ngày

### Description

DB scaffolding + welcome copy + operator view cho 50 founding member với 50% lifetime discount promise.

### Layer

- `services/founding/founding_member_service.py` (new)
- `bot/handlers/founding_handler.py` (new)
- `bot/handlers/start_handler.py` (extend)
- `content/onboarding/founding_welcome.yaml` (new)
- `docs/current/founding-promise.md` (new — promise document)

### Acceptance Criteria

- [ ] **Sequence assignment atomic**: dùng `SELECT ... FOR UPDATE` hoặc advisory lock — race-safe khi 2 user redeem cùng giây
- [ ] **Founding welcome banner** (trong `founding_welcome.yaml`):
  > *"🌱 Bạn là Founding Member #[N] của Bé Tiền — 1 trong 50 người đầu tiên.*
  > *Trong giai đoạn này toàn bộ tính năng miễn phí.*
  > *Khi Bé Tiền Pro ra mắt chính thức (dự kiến cuối 2026), bạn được giảm 50% trọn đời — 44.000đ/tháng thay vì 88.000đ — để cảm ơn sự đồng hành."*
- [ ] **`/whoami`** command: trả về user info (wealth_segment, onboarding date, founding sequence nếu có, days active)
- [ ] **`/founding_status`** operator command: liệt kê 50 founding member với sequence, ngày onboard, days active, last seen
- [ ] **`compute_discount(user_id)`** service method ready cho Phase 5.7 (return 0.5 nếu founding, 0 nếu không)
- [ ] **Founding badge** xuất hiện trong:
  - [ ] Welcome message (1 lần khi onboard)
  - [ ] `/whoami` output
  - [ ] Shareable Twin image (#B.1)
  - [ ] Operator feedback inbox (#A.7)
- [ ] **`docs/current/founding-promise.md`** document:
  - [ ] Promise statement
  - [ ] Expiry: none (lifetime)
  - [ ] Exception cases (vd: nếu user delete account và tạo lại)
  - [ ] Owner: Founder/PM
  - [ ] Reference link từ Phase 5.7 detailed (TBD khi viết 5.7)

### Dependencies

- Depends on: Migration `4.1.04` (is_founding_member, founding_member_sequence, grants_founding_status)

---

## INFRA / MIGRATION TASKS

### TASK #M.1: Migration `4.1.01_user_cost_budgets`

**Type:** Task
**Labels:** `phase-4.1`, `infra`, `migration`, `priority-p0`
**Estimate:** 0.25 ngày

- [ ] Create table `user_cost_budgets` với `CHECK CONSTRAINT chk_tier_v1` (tier IN 'free', 'pro')
- [ ] Create table `llm_cost_log` với indexes
- [ ] Apply dev + staging
- [ ] Verify rollback script

### TASK #M.2: Migration `4.1.02_feedback_sla_index`

**Type:** Task
**Labels:** `phase-4.1`, `infra`, `migration`, `priority-p0`
**Estimate:** 0.1 ngày

- [ ] Create partial index `idx_feedback_unanswered_age`
- [ ] Add columns `first_responded_at`, `sla_breach_alerted_at`, `onboarding_emoji_signal`
- [ ] Apply dev + staging

### TASK #M.3: Migration `4.1.03_twin_calibration_log`

**Type:** Task
**Labels:** `phase-4.1`, `infra`, `migration`, `priority-p1`
**Estimate:** 0.1 ngày

- [ ] Create table `twin_calibration_snapshots`
- [ ] Create index `idx_twin_calibration_due` (partial)
- [ ] Apply dev + staging

### TASK #M.4: Migration `4.1.04_founding_member_flag`

**Type:** Task
**Labels:** `phase-4.1`, `infra`, `migration`, `priority-p0`
**Estimate:** 0.25 ngày

- [ ] Alter `users` table: add `is_founding_member`, `founding_member_sequence`, `founding_member_at`
- [ ] Alter `invite_codes`: add `grants_founding_status`
- [ ] Create index `idx_users_founding` (partial)
- [ ] Create table `onboarding_sessions` với index `idx_onboarding_stuck`
- [ ] Apply dev + staging

---

## DEPLOY READINESS TASKS

### TASK #D.1: Verify `ZALO_CHANNEL_ENABLED=false`

**Type:** Task
**Labels:** `phase-4.1`, `deploy`, `priority-p0`
**Estimate:** 0.1 ngày

- [ ] Grep codebase: tất cả Zalo router init phải gate qua flag
- [ ] Deploy config (env var) check 2 lần trước launch
- [ ] Document trong `docs/current/phase-4.1/deploy-checklist.md`

### TASK #D.2: Operator briefing & dogfood

**Type:** Task
**Labels:** `phase-4.1`, `deploy`, `priority-p0`
**Estimate:** 0.5 ngày

- [ ] Operator (= founder) tự onboard từ 3 invite test code với 3 source khác nhau
- [ ] Verify E2E flow đầy đủ: onboarding → Twin → feedback → next morning briefing
- [ ] Verify KPI digest đến hộp tin sáng hôm sau
- [ ] Verify feedback SLA alert hoạt động (tạo feedback test, đợi 24h, hoặc set fake `created_at`)

### TASK #D.3: 50 invite link distribution package

**Type:** Task
**Labels:** `phase-4.1`, `deploy`, `priority-p0`
**Estimate:** 0.5 ngày

- [ ] Generate 50 invite via `scripts/soft_launch_acquisition.py`
- [ ] Verify mỗi link unique, `grants_founding_status=TRUE`
- [ ] Export CSV với assignment plan (link nào gửi cho ai)
- [ ] Operator review distribution list trước khi gửi

---

## SUMMARY

| Type | Count | Total Estimate |
|---|---|---|
| Epics | 3 | — |
| Stories | 13 | ~13 ngày |
| Migration tasks | 4 | ~0.7 ngày |
| Deploy tasks | 3 | ~1.1 ngày |
| **Total** | **23 issues** | **~15 ngày work (3 tuần với buffer)** |

### Critical path

`#M.1 → #A.3 → #A.5 → #A.6 → ready for ops`
`#M.4 → #A.1 → #A.2 → #A.8 → ready for users`
`#M.4 → #C.1 → #C.4 → ready for launch`
`#C.2 + #C.3 → ready for measurement`

All must converge before 50-user soft launch start.
