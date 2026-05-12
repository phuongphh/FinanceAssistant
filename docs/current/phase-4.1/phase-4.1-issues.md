# Phase 4.1 — GitHub Issues

> **Phase:** 4.1 — Pre-Launch Hardening
> **Reference:** [`phase-4.1-detailed.md`](./phase-4.1-detailed.md)
> **Total:** 3 Epics, 12 Stories, ~3 tuần.

## Phase Overview

Phase 4.1 đưa Bé Tiền sang trạng thái production-ready cho soft launch tháng 6/2026. Không thêm wow-feature; siết 3 trục: first-session UX, cost guardrail, observability + feedback triage. Thêm 2 Twin polish lấy từ dogfood Phase 4A và 1 playbook cho operator.

### Scope decisions locked

- 50-user soft launch tháng 6/2026, không scale rộng hơn.
- Budget cap default rộng tay (free = 30k VND/tháng) — phase này chỉ stop the bleeding, không monetize.
- Sentry + KPI digest wire ngay tuần 1, không defer.
- Shareable Twin image **không** chứa số tuyệt đối + **không** auto-prompt share.
- Calibration framing honest (kể cả khi hit-rate thấp), không inflate.
- Tier multi-user (free/pro/cfo) ở DB schema, nhưng UI/flow defer sang Phase 5.7.

---

# Epic A: Pre-Launch Hardening

**Labels:** `phase-4.1`, `epic`, `hardening`
**Estimate:** ~1.5 tuần (7 stories)
**Goal:** Đưa onboarding, cost control, observability, và feedback triage lên mức production-grade trước soft launch.
**Stories:** A.1, A.2, A.3, A.4, A.5, A.6, A.7

---

## [Story] P4.1-A1: Onboarding redesign — 3-step guided flow

**Labels:** `phase-4.1`, `story`, `onboarding`, `frontend`
**Parent:** Epic A
**Estimate:** 2 ngày

### Description

Rewrite `/start` thành flow 3 bước dẫn dắt, đảm bảo user thấy giá trị Bé Tiền (Twin) ngay session đầu thay vì lạc trong menu.

### Acceptance Criteria

- [ ] `/start` lần đầu hiển thị welcome message < 200 chars + inline button "🌱 Bắt đầu hành trình".
- [ ] Sau khi bấm, 3 bước hiện rõ với progress `(1/3)`, `(2/3)`, `(3/3)` ở đầu message:
  - [ ] Bước 1: chọn wealth level (4 button — Khởi Đầu / Trẻ Năng Động / Trung Lưu Vững / Tinh Hoa).
  - [ ] Bước 2: thêm asset đầu tiên — có nút "Để Bé Tiền dùng demo trước" để skip + tạo placeholder asset (cash 50tr).
  - [ ] Bước 3: trigger first-Twin compute (handoff cho Story A.2).
- [ ] User cũ (`created_at < deploy_date`) không bị qua flow mới.
- [ ] Toàn bộ string nằm trong `content/onboarding/welcome_v2.yaml`, pass `vi-localization-checker`.
- [ ] Feature flag `ONBOARDING_V2_ENABLED` env var, default true.

### Technical Notes

- Reuse `intent_logs` để track step completion: action `(onboarding, step_1_done)` etc.
- Wealth level selection nên reuse existing `user_profile_service.set_wealth_level()`.
- Placeholder asset = `Asset(type='cash', value=50_000_000, label='Tiền mặt demo', user_id=...)`.

### Dependencies

- None (foundation story).

---

## [Story] P4.1-A2: First-Twin shortcut

**Labels:** `phase-4.1`, `story`, `onboarding`, `twin`
**Parent:** Epic A
**Estimate:** 1.5 ngày

### Description

Sau khi user xong onboarding step 2, auto-trigger Twin computation và push kết quả message thứ 3 — KHÔNG bắt user đi tìm menu.

### Acceptance Criteria

- [ ] `OnboardingService.complete_step_2()` async-trigger `TwinEngineService.compute_for_user(user_id)`.
- [ ] Khi result ready, push qua Notifier với message intro từ `content/onboarding/first_twin_intro.yaml`.
- [ ] Time-to-first-Twin (từ `/start` đến message hiển thị cone) ≤ 5 phút — đo qua `users.created_at` vs `intent_logs (twin, first_view)`.
- [ ] Twin compute fail → fallback message "đang tính, quay lại sau 1 phút nhé" + auto-retry sau 60s 1 lần.
- [ ] Onboarding completion log `(onboarding, completed)` vào `intent_logs`.

### Technical Notes

- Twin compute hiện ~10-30s với 1000 Monte Carlo paths. Async background task, không block.
- Fallback message phải có timestamp để debug nếu user phản hồi.

### Dependencies

- P4.1-A1 (onboarding flow).

---

## [Story] P4.1-A3: Cost guardrail middleware

**Labels:** `phase-4.1`, `story`, `cost`, `infrastructure`
**Parent:** Epic A
**Estimate:** 2 ngày

### Description

Mọi LLM call (DeepSeek/Claude/Whisper) đi qua `cost_tracking_adapter` để enforce per-user monthly budget cap.

### Acceptance Criteria

- [ ] Migration `4.1.01_user_cost_budgets.py` applied — tables `user_cost_budgets` + `llm_cost_log`.
- [ ] `cost_tracking_adapter` wrap DeepSeek/Claude/Whisper adapter hiện có; mọi call qua adapter này.
- [ ] Trước mỗi call, `BudgetService.check_and_reserve(user_id, estimated_cost)`:
  - [ ] Nếu spend < 80% cap → cho qua silent.
  - [ ] Nếu vừa qua 80% → cho qua + push warning ấm áp (1 lần/tháng).
  - [ ] Nếu chạm 100% → raise `BudgetExceededError`, service catch và trả message "tháng này Bé Tiền tạm dừng tính năng X".
- [ ] Sau mỗi call, log vào `llm_cost_log` với provider/operation/tokens_in/tokens_out/cost_vnd/latency_ms.
- [ ] Default cap: free = 30,000 VND, pro = 150,000 VND, cfo = 400,000 VND. Tier hiện tại all = `free`.
- [ ] Operator command `/budget_set <user_id_or_telegram_id> <amount_vnd>` để override 1-1.
- [ ] Integration test cover: under-budget pass, 80% warning trigger, 100% block.

### Technical Notes

- Pricing reference: DeepSeek $0.14/1M input + $0.28/1M output ≈ 6 VND/1k token. Claude Sonnet $3/1M input ≈ 75 VND/1k token (OCR only).
- Estimate cost trước call bằng `tokens_in_estimated = len(prompt) // 4`, `tokens_out_estimated = max_tokens param`.
- `BudgetService.check_and_reserve` chỉ flush, worker commit.

### Dependencies

- None.

---

## [Story] P4.1-A4: Daily cost report

**Labels:** `phase-4.1`, `story`, `cost`, `observability`
**Parent:** Epic A
**Estimate:** 0.5 ngày

### Description

Cron 8:00 ICT mỗi sáng gửi operator báo cáo cost 24h trước.

### Acceptance Criteria

- [ ] `cost_report_service.generate_daily_report(date)` trả Markdown ngắn (< 500 chars):
  - Tổng cost theo provider (DeepSeek/Claude/Whisper).
  - Top 5 user theo cost.
  - User mới chạm 80% cap trong 24h.
- [ ] Số tròn về 1k VND.
- [ ] Nếu tổng cost ngày > 200% trung bình 7 ngày → flag 🚨 đầu message.
- [ ] Sent qua Notifier đến `OPERATOR_TELEGRAM_ID`.
- [ ] Tích hợp vào KPI digest (Story A.6) — 1 message duy nhất buổi sáng.

### Technical Notes

- Reuse `llm_cost_log` từ A.3, không cần bảng mới.
- Báo cáo + KPI digest share cùng cron worker.

### Dependencies

- P4.1-A3 (cost log).
- P4.1-A6 (digest infrastructure).

---

## [Story] P4.1-A5: Sentry + LLM metrics dashboard

**Labels:** `phase-4.1`, `story`, `observability`, `infrastructure`
**Parent:** Epic A
**Estimate:** 1 ngày

### Description

Wire Sentry vào FastAPI + workers, expose LLM metrics đủ để build dashboard Grafana/Metabase.

### Acceptance Criteria

- [ ] Sentry SDK init trong `main.py` lifecycle + mỗi worker entrypoint.
- [ ] Unhandled exception capture với `user_id` + `intent_name` tag.
- [ ] PII scrub: `before_send` hook strip regex số > 6 digit, email, phone; whitelist field thay vì blacklist.
- [ ] ENV `SENTRY_DSN` documented trong `.env.example`; empty string = disabled.
- [ ] LLM metrics adapter ghi mỗi call: provider/operation/latency_ms/success/model_version vào `llm_cost_log`.
- [ ] Operator có dashboard query-ready (SQL examples committed trong `docs/operations/sentry-queries.md` hoặc Metabase saved questions):
  - Error rate per intent (last 24h).
  - p50/p95 LLM latency per provider.
  - Daily active users.
- [ ] Test exception trong staging capture được trên Sentry web UI.

### Technical Notes

- Sentry SDK version pinned trong `pyproject.toml`.
- Sample rate 100% cho phase soft launch (50 user, traffic thấp).

### Dependencies

- P4.1-A3 (cost log table reused for metrics).

---

## [Story] P4.1-A6: Daily KPI digest cron

**Labels:** `phase-4.1`, `story`, `observability`, `worker`
**Parent:** Epic A
**Estimate:** 1 ngày

### Description

Cron 8:00 ICT mỗi sáng gửi operator KPI tổng hợp (gộp với cost report A.4).

### Acceptance Criteria

- [ ] `daily_kpi_digest_worker` chạy 8:00 ICT mỗi ngày qua scheduler.
- [ ] Gửi 1 message Telegram đến `OPERATOR_TELEGRAM_ID` với:
  - DAU / WAU / MAU.
  - Số Twin view 24h.
  - Intent classification accuracy (% confirm vs % clarify, từ `intent_logs`).
  - Churn signals: user không active 7+ ngày, đếm số.
  - Top 3 feedback chưa trả lời (snippet 100 chars + age).
  - Cost report (từ A.4).
- [ ] Length < 2000 chars, Markdown formatted.
- [ ] Cron fail → Sentry alert, không silent.
- [ ] Script `scripts/kpi_digest.py` runnable standalone với arg `--date YYYY-MM-DD` để backfill.

### Technical Notes

- Scheduler: APScheduler hoặc cron OS-level — chọn cái codebase đang dùng.
- Query intent accuracy: `SELECT COUNT(*) FILTER (WHERE action='confirm') / COUNT(*) FROM intent_logs WHERE date = ...`.

### Dependencies

- P4.1-A3 (cost log).
- P4.1-A7 (feedback inbox query).

---

## [Story] P4.1-A7: Feedback triage UI

**Labels:** `phase-4.1`, `story`, `feedback`, `operator-tools`
**Parent:** Epic A
**Estimate:** 1.5 ngày

### Description

Operator có command để xem feedback pending, reply qua bot, và worker alert nếu SLA breach.

### Acceptance Criteria

- [ ] Migration `4.1.02_feedback_sla_index.py` applied — partial index + `first_responded_at`, `sla_breach_alerted_at`.
- [ ] `/feedback_inbox` cho operator: list feedback `status=open` cũ nhất trước, mỗi entry hiện ID/wealth level/snippet/age.
- [ ] `/feedback_reply <id> <message>` gửi message đó cho user via Notifier, set `first_responded_at = NOW()`, `status = answered`.
- [ ] `/feedback_reply <id> --template <name>` dùng template từ `content/feedback/triage_responses.yaml` (5 template: thanks_logged, will_fix_next_phase, need_more_info, wont_fix_with_reason, escalate_owner).
- [ ] `feedback_sla_worker` chạy mỗi giờ, alert operator nếu feedback `status=open` quá 24h (chỉ alert 1 lần per feedback).
- [ ] Permission check: chỉ `OPERATOR_TELEGRAM_ID` được dùng `/feedback_*`.

### Technical Notes

- Reply qua Notifier port, KHÔNG import telegram_service trực tiếp.
- Template format dùng `{{user_name}}`, `{{wealth_level_vn}}` placeholder.

### Dependencies

- None (existing `/feedback` từ Phase 3.8.5).

---

# Epic B: Twin Polish Thực Chiến

**Labels:** `phase-4.1`, `epic`, `twin`
**Estimate:** ~1 tuần (2 stories)
**Goal:** Lấy 2 user request lớn nhất từ Phase 4A dogfood — shareable moment + predictions vs actual — để build trust trước launch.
**Stories:** B.1, B.2

---

## [Story] P4.1-B1: Shareable Twin image

**Labels:** `phase-4.1`, `story`, `twin`, `image`
**Parent:** Epic B
**Estimate:** 2 ngày

### Description

Trong Twin view, thêm nút "📸 Lưu thành ảnh" trả về PNG render của cone chart + summary text, KHÔNG chứa số tuyệt đối.

### Acceptance Criteria

- [ ] Nút "📸 Lưu thành ảnh" trong Twin Telegram view.
- [ ] Bấm → service gen PNG (target < 1s) qua PIL/Pillow.
- [ ] Content image:
  - Cone chart (P10/P50/P90 lines).
  - % tăng trưởng compounded (vd "+86% trong 10 năm").
  - Time horizon ("Bé Tiền 2036").
  - Bé Tiền mascot góc dưới phải.
  - Watermark "Bé Tiền — Personal CFO" mờ ở bottom.
- [ ] **KHÔNG** hiển thị số tiền tuyệt đối (kể cả P50).
- [ ] **KHÔNG** auto-prompt share lên FB/Zalo — user tự save.
- [ ] Render headless, không depend Chrome/Puppeteer.
- [ ] Feature flag `TWIN_SHARE_IMAGE_ENABLED`, default true.

### Technical Notes

- PIL/Pillow + matplotlib for chart, rasterize to PNG 1080x1080.
- Font Vietnamese-safe (Inter hoặc Be Vietnam Pro), embed trong repo.

### Dependencies

- None (Twin view đã có từ 4A).

---

## [Story] P4.1-B2: Predictions vs actual calibration

**Labels:** `phase-4.1`, `story`, `twin`, `trust`
**Parent:** Epic B
**Estimate:** 2.5 ngày

### Description

Mỗi Twin view log snapshot, worker check sau 7d/30d/90d so với actual net worth. Hiện hit-rate trong Twin view khi đủ data.

### Acceptance Criteria

- [ ] Migration `4.1.03_twin_calibration_log.py` applied.
- [ ] Mỗi lần Twin compute, service log snapshot vào `twin_calibration_snapshots` với horizon 7/30/90 ngày.
- [ ] `twin_calibration_worker` daily: với mỗi snapshot due, fill `actual_vnd` từ current net worth, compute `within_band` (P10 ≤ actual ≤ P90).
- [ ] Twin view thêm section "🎯 Bé Tiền đoán đúng bao nhiêu?" — chỉ hiển thị khi user có ≥ 3 snapshot completed.
- [ ] Framing honest: "Bé Tiền đoán đúng 7/9 lần (78%)". Nếu hit-rate < 50% → hiện disclaimer "dự phóng chưa chuẩn, Bé Tiền đang học thêm".
- [ ] Backfill script `twin_calibration_backfill.py` replay Twin runs từ 30 ngày trước để bootstrap data.

### Technical Notes

- Within-band định nghĩa scope rộng: P10 ≤ actual ≤ P90 (80% confidence interval).
- Snapshot lưu cả 3 horizon, worker query bằng `WHERE predicted_at + horizon_days <= NOW()`.

### Dependencies

- None.

---

# Epic C: Soft Launch Playbook

**Labels:** `phase-4.1`, `epic`, `launch`, `documentation`
**Estimate:** ~3-5 ngày (3 stories)
**Goal:** Operator có công cụ + tiêu chí rõ ràng để chạy 50-user soft launch.
**Stories:** C.1, C.2, C.3

---

## [Story] P4.1-C1: Acquisition source + invite tracking

**Labels:** `phase-4.1`, `story`, `launch`, `analytics`
**Parent:** Epic C
**Estimate:** 1 ngày

### Description

Generate 50 unique invite link với metadata source, track user acquisition để biết kênh nào hiệu quả.

### Acceptance Criteria

- [ ] Table `invite_codes (token PK, source, batch_name, used_by_user_id, created_at, used_at)`.
- [ ] Script `soft_launch_acquisition.py generate --source <name> --count <n>` tạo invite codes, in ra CSV.
- [ ] `start_handler` parse `?start=invite_<token>`, lookup, fill `users.acquisition_source` + mark token used.
- [ ] Operator command `/cohort_stats` hiển thị breakdown user theo source + signup count.
- [ ] Source ban đầu: `friends`, `personal_fb`, `vn_finance_community`, `direct_msg`.

### Technical Notes

- Token = 8 char URL-safe random.
- 1 token = 1 user; nếu user dùng token đã used → ignore, dùng default `acquisition_source = 'organic'`.

### Dependencies

- None.

---

## [Story] P4.1-C2: Success metrics rubric

**Labels:** `phase-4.1`, `story`, `documentation`, `launch`
**Parent:** Epic C
**Estimate:** 0.5 ngày

### Description

Document 6 success metric với target + SQL query để compute.

### Acceptance Criteria

- [ ] File `docs/current/phase-4.1/success-metrics.md` committed.
- [ ] 6 metric documented:
  - D1 retention ≥ 70%
  - D7 retention ≥ 40%
  - % user mở Twin trong session đầu ≥ 70%
  - % user log ≥ 1 asset thật trong 7 ngày đầu ≥ 60%
  - Intent classification accuracy ≥ 85%
  - Feedback SLA (response < 24h) ≥ 95%
- [ ] Mỗi metric có: định nghĩa rõ ràng, target, SQL query để compute từ existing tables, cron tích hợp (hoặc on-demand).

### Dependencies

- P4.1-A6 (KPI digest có thể reuse query).

---

## [Story] P4.1-C3: Kill criteria documentation

**Labels:** `phase-4.1`, `story`, `documentation`, `launch`
**Parent:** Epic C
**Estimate:** 0.5 ngày

### Description

Document tiêu chí dừng/pivot rõ ràng cho 4-week post-launch checkpoint.

### Acceptance Criteria

- [ ] File `docs/current/phase-4.1/kill-criteria.md` committed.
- [ ] Mỗi tiêu chí có: threshold rõ ràng, owner, action plan, measurement method:
  - 4-week retention < 20% → pivot positioning hoặc kill product.
  - Cost per active user > 50k VND/tháng sau 1 tháng → re-evaluate LLM budget.
  - Critical bug rate (Sentry P1) > 1/day với cohort 50 user → freeze feature, fix sprint.
  - Bé Tiền persona violation reported > 5 lần/tuần → prompt audit toàn bộ.
- [ ] Document có timeline: T+7, T+14, T+28 checkpoint.

### Dependencies

- P4.1-C2 (metric definition).

---

## Summary Table

| Story ID | Title | Epic | Estimate | Critical Path |
|---|---|---|---|---|
| P4.1-A1 | Onboarding redesign — 3-step guided flow | A | 2d | ✅ |
| P4.1-A2 | First-Twin shortcut | A | 1.5d | ✅ |
| P4.1-A3 | Cost guardrail middleware | A | 2d | ✅ |
| P4.1-A4 | Daily cost report | A | 0.5d | — |
| P4.1-A5 | Sentry + LLM metrics dashboard | A | 1d | ✅ |
| P4.1-A6 | Daily KPI digest cron | A | 1d | ✅ |
| P4.1-A7 | Feedback triage UI | A | 1.5d | — |
| P4.1-B1 | Shareable Twin image | B | 2d | — |
| P4.1-B2 | Predictions vs actual calibration | B | 2.5d | — |
| P4.1-C1 | Acquisition source + invite tracking | C | 1d | — |
| P4.1-C2 | Success metrics rubric | C | 0.5d | ✅ |
| P4.1-C3 | Kill criteria documentation | C | 0.5d | — |

**Total estimate:** ~16 ngày làm việc (3 tuần với buffer).
