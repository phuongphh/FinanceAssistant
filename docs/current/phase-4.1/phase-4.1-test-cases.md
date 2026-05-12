<!-- testing-signoff: need to be signed -->

# Phase 4.1 — Test Cases

> **Phase:** 4.1 — Pre-Launch Hardening
> **Reference:** [`phase-4.1-detailed.md`](./phase-4.1-detailed.md), [`phase-4.1-issues.md`](./phase-4.1-issues.md)
> **Tester profile:** Operator/founder dogfood + 1-2 trusted user trên staging.

## Purpose

Pass-criteria cho Phase 4.1 trước khi soft launch tháng 6/2026. Vì 4.1 là **hardening phase** (không feature mới), test cases focus vào: (1) first-session flow không trượt, (2) cost guardrail không chặn nhầm + chặn được spammer thật, (3) observability ghi nhận đúng, (4) feedback SLA chạy được.

Khi tất cả test cases pass:
- Đổi `<!-- testing-signoff: need to be signed -->` → `<!-- testing-signoff: signed -->`.
- Sign-Off table cuối file điền đủ tester + date.
- Trigger archive workflow auto-move folder sang `docs/archive/phase-4.1/`.

---

## How to Use

- Mỗi test case format: `### TC-XXX: Title` với Type / Story / Persona / Preconditions / Steps / Expected / Pass.
- **Type:** `unit` (auto pytest) / `integration` (qua bot trên staging) / `e2e` (full user journey) / `manual` (operator dogfood).
- **Pass marker:** ✅ pass / ❌ fail / ⏸️ blocked / 🟡 partial.
- Khi fail: ghi root cause + GitHub issue link.

---

## Test Data Setup — 5 Personas

Reuse 5 persona đã có từ Phase 4A test (cùng telegram_id để giữ state):

1. **Hà** — Wealth level: Trẻ Năng Động (~140tr net worth). Portfolio: VCB stock + USDT crypto + 30tr cash. Đã onboard từ Phase 3A. Active daily.
2. **Anh Phương** — Wealth level: Trung Lưu Vững (~480tr). Portfolio: 5 cổ phiếu VN + 100tr gold + nhà 2 tỷ (placeholder). Đã ship Twin từ 4A. Power user.
3. **Chị Hằng** — Wealth level: Tinh Hoa (~2.4 tỷ). Multi-asset, multi-currency. Hay test edge case.
4. **Em Khôi** — Wealth level: Khởi Đầu (~12tr). Sinh viên, mới onboard. Hay quên dùng bot.
5. **Persona Mới** — Account clean (Telegram ID chưa từng `/start`). Zero portfolio. Dùng để test onboarding flow A.1/A.2.

---

## Epic A — Pre-Launch Hardening

### TC-001: Onboarding 3-step happy path (real asset)

- **Type:** e2e
- **Story:** P4.1-A1, P4.1-A2
- **Persona:** Mới
- **Preconditions:** Account Telegram chưa từng `/start` Bé Tiền. Staging có ENV `ONBOARDING_V2_ENABLED=true`.
- **Steps:**
  1. Gõ `/start`.
  2. Bấm nút "🌱 Bắt đầu hành trình".
  3. Step 1: chọn "Trẻ Năng Động (30-200tr)".
  4. Step 2: bấm "Thêm tài sản đầu tiên" → nhập "VCB 100 cổ".
  5. Step 3: chờ Twin message.
- **Expected:**
  - Mỗi step có progress chip `(1/3)`, `(2/3)`, `(3/3)`.
  - Step 1 hiển thị 4 wealth level button đúng (Khởi Đầu / Trẻ Năng Động / Trung Lưu Vững / Tinh Hoa).
  - Asset được lưu vào DB với đúng user_id.
  - Twin message xuất hiện trong < 5 phút từ `/start`, có cone P10/P50/P90 với data thật.
  - `intent_logs` có entry `(onboarding, completed)`.
- **Pass:** ⏸️

### TC-002: Onboarding skip với placeholder demo

- **Type:** e2e
- **Story:** P4.1-A1, P4.1-A2
- **Persona:** Mới (account khác TC-001)
- **Preconditions:** Account clean.
- **Steps:**
  1. `/start` → "🌱 Bắt đầu hành trình".
  2. Step 1: chọn "Khởi Đầu (0-30tr)".
  3. Step 2: bấm "Để Bé Tiền dùng demo trước".
  4. Đợi Twin message.
- **Expected:**
  - Placeholder asset tạo: `cash, 50tr VND, label="Tiền mặt demo"`.
  - Twin message có disclaimer "đây là demo, hãy thêm tài sản thật để Twin chính xác hơn".
  - Time-to-Twin < 3 phút (faster vì không cần input).
- **Pass:** ⏸️

### TC-003: User cũ không bị qua flow mới

- **Type:** manual
- **Story:** P4.1-A1
- **Persona:** Hà
- **Preconditions:** Hà đã onboard từ Phase 3A. `users.created_at` < deploy_date.
- **Steps:**
  1. Hà gõ `/start` lại sau deploy 4.1.
- **Expected:**
  - Hà nhận welcome message cũ (không phải welcome_v2).
  - Không có progress chip 3-step.
- **Pass:** ⏸️

### TC-004: Twin compute fail fallback

- **Type:** integration
- **Story:** P4.1-A2
- **Persona:** Mới
- **Preconditions:** Mock DeepSeek timeout trong onboarding test env.
- **Steps:**
  1. `/start` → đi qua 3 step.
  2. Step 3 trigger Twin → DeepSeek fail.
- **Expected:**
  - Fallback message "đang tính, quay lại sau 1 phút nhé" hiện trong 5s.
  - Auto-retry sau 60s success → push Twin result.
  - Không spam fallback message nhiều lần.
- **Pass:** ⏸️

### TC-005: Budget cap — under 80% pass silent

- **Type:** integration
- **Story:** P4.1-A3
- **Persona:** Em Khôi
- **Preconditions:** `user_cost_budgets` row cho Em Khôi: `monthly_cap_vnd=30000`, `current_month_spend_vnd=10000`.
- **Steps:**
  1. Em Khôi hỏi 1 câu intent classify (cost ~50 VND).
- **Expected:**
  - LLM call success, response trả về.
  - `llm_cost_log` có entry mới.
  - `current_month_spend_vnd` tăng ~50 VND.
  - Không có warning message gửi cho user.
- **Pass:** ⏸️

### TC-006: Budget cap — 80% warning trigger 1 lần

- **Type:** integration
- **Story:** P4.1-A3
- **Persona:** Chị Hằng
- **Preconditions:** `current_month_spend_vnd=23000`, `monthly_cap_vnd=30000`, `last_warning_sent_at=NULL`.
- **Steps:**
  1. Chị Hằng trigger 1 LLM call cost ~2000 VND → spend lên 25000 (83%).
  2. Trigger thêm 1 LLM call nữa.
- **Expected:**
  - Sau call 1: user nhận message warning ấm áp ("Bé Tiền nhắc nhỏ: tháng này bạn đã dùng 83% budget...").
  - `last_warning_sent_at` updated.
  - Sau call 2: LLM call vẫn pass, KHÔNG gửi warning lần 2.
- **Pass:** ⏸️

### TC-007: Budget cap — 100% block

- **Type:** integration
- **Story:** P4.1-A3
- **Persona:** Chị Hằng (giả định đã spam test)
- **Preconditions:** `current_month_spend_vnd=30000`, `monthly_cap_vnd=30000`.
- **Steps:**
  1. Chị Hằng hỏi 1 intent câu.
- **Expected:**
  - LLM call bị từ chối — `BudgetExceededError` raise.
  - User nhận message "tháng này Bé Tiền tạm dừng tính năng X cho bạn, sang tháng mở lại" + suggest `/feedback`.
  - Không có entry mới trong `llm_cost_log` (call không xảy ra).
  - `current_month_spend_vnd` không tăng.
- **Pass:** ⏸️

### TC-008: Operator override budget

- **Type:** manual
- **Story:** P4.1-A3
- **Persona:** Anh Phương
- **Preconditions:** Anh Phương spend 30000/30000 (100%). Operator nhận warning từ daily report.
- **Steps:**
  1. Operator gõ `/budget_set @anh_phuong 100000` trong bot.
  2. Anh Phương hỏi 1 câu.
- **Expected:**
  - Operator nhận confirm "Đã set budget Anh Phương = 100,000 VND".
  - `user_cost_budgets` updated.
  - Anh Phương's next call pass.
- **Pass:** ⏸️

### TC-009: Daily cost report — normal day

- **Type:** integration
- **Story:** P4.1-A4
- **Persona:** Operator
- **Preconditions:** Yesterday có 50 LLM call, tổng ~5000 VND, 4 user active.
- **Steps:**
  1. Run `python scripts/kpi_digest.py --date 2026-05-13` manually.
- **Expected:**
  - Operator nhận Telegram message < 500 chars.
  - Breakdown DeepSeek/Claude/Whisper rõ ràng.
  - Top 5 user listed.
  - Không có flag 🚨 (vì dưới 200% baseline).
- **Pass:** ⏸️

### TC-010: Daily cost report — spike day

- **Type:** integration
- **Story:** P4.1-A4
- **Persona:** Operator
- **Preconditions:** Inject test data: yesterday spend = 50000 VND, 7-day avg = 5000 VND → 1000% spike.
- **Steps:**
  1. Run digest script.
- **Expected:**
  - Message bắt đầu bằng "🚨 Cost spike phát hiện ngày 2026-05-13:".
  - Highlight user nào đẩy spike.
- **Pass:** ⏸️

### TC-011: Sentry capture exception

- **Type:** manual
- **Story:** P4.1-A5
- **Persona:** Anh Phương
- **Preconditions:** Sentry DSN configured trong staging.
- **Steps:**
  1. Trigger 1 known bug (vd hỏi câu mà handler raise unhandled exception).
- **Expected:**
  - Sentry web UI hiển thị exception trong < 30s.
  - Tag có `user_id` (UUID, không phải Telegram ID hay tên).
  - Stack trace complete.
- **Pass:** ⏸️

### TC-012: Sentry PII scrub

- **Type:** unit
- **Story:** P4.1-A5
- **Persona:** N/A
- **Preconditions:** Sentry adapter test fixture.
- **Steps:**
  1. Trigger exception với context `{"message": "tôi có 1500000 VND", "email": "user@x.com"}`.
- **Expected:**
  - Before_send hook strip:
    - `1500000` → `[redacted_number]`.
    - `user@x.com` → `[redacted_email]`.
  - Event sent to Sentry không chứa raw money/email.
- **Pass:** ⏸️

### TC-013: KPI digest morning send

- **Type:** integration
- **Story:** P4.1-A6
- **Persona:** Operator
- **Preconditions:** Cron scheduled 8:00 ICT. Staging có data 24h trước (5 user, 20 message).
- **Steps:**
  1. Đợi cron chạy 8:00 (hoặc trigger manual).
- **Expected:**
  - Operator nhận message < 2000 chars.
  - Bao gồm: DAU/WAU/MAU, Twin view count, intent accuracy %, churn list, top 3 feedback open, cost summary.
  - Markdown render đẹp trên Telegram.
- **Pass:** ⏸️

### TC-014: Feedback inbox và reply

- **Type:** e2e
- **Story:** P4.1-A7
- **Persona:** Em Khôi + Operator
- **Preconditions:** Em Khôi gửi `/feedback` "Twin của em sao thấp thế?".
- **Steps:**
  1. Operator gõ `/feedback_inbox`.
  2. Operator gõ `/feedback_reply <id> Bé Tiền sẽ check giúp bạn nhé.`.
- **Expected:**
  - Inbox hiển thị feedback của Em Khôi với age "vài phút trước", wealth_level=Khởi Đầu.
  - Em Khôi nhận message reply từ Bé Tiền.
  - `feedbacks.first_responded_at` = NOW, `status='answered'`.
- **Pass:** ⏸️

### TC-015: Feedback reply template

- **Type:** integration
- **Story:** P4.1-A7
- **Persona:** Hà + Operator
- **Preconditions:** Hà có feedback open: "Cảm ơn Bé Tiền nhé".
- **Steps:**
  1. Operator gõ `/feedback_reply <id> --template thanks_logged`.
- **Expected:**
  - Hà nhận message template (chứa `{{user_name}}` đã substitute).
  - Persona "Bé Tiền" giữ nguyên (ấm áp, không cứng).
- **Pass:** ⏸️

### TC-016: Feedback SLA breach alert

- **Type:** integration
- **Story:** P4.1-A7
- **Persona:** Em Khôi + Operator
- **Preconditions:** Em Khôi feedback open `created_at = NOW() - 25 hours`. `sla_breach_alerted_at = NULL`.
- **Steps:**
  1. Đợi `feedback_sla_worker` chạy (hourly cron).
- **Expected:**
  - Operator nhận alert "🚨 Feedback của Em Khôi đã pending 25h, cần phản hồi gấp".
  - `sla_breach_alerted_at` updated → không alert lặp lại lần sau.
- **Pass:** ⏸️

### TC-017: Permission check feedback commands

- **Type:** integration
- **Story:** P4.1-A7
- **Persona:** Anh Phương (non-operator)
- **Preconditions:** Anh Phương không phải `OPERATOR_TELEGRAM_ID`.
- **Steps:**
  1. Anh Phương gõ `/feedback_inbox`.
- **Expected:**
  - Bot trả "Lệnh này không khả dụng" hoặc im lặng (không leak rằng có command như vậy).
  - Anh Phương KHÔNG thấy feedback của user khác.
- **Pass:** ⏸️

---

## Epic B — Twin Polish Thực Chiến

### TC-018: Shareable Twin image render

- **Type:** integration
- **Story:** P4.1-B1
- **Persona:** Anh Phương
- **Preconditions:** Twin của Anh Phương đã compute, có cone data.
- **Steps:**
  1. Anh Phương mở Twin view.
  2. Bấm "📸 Lưu thành ảnh".
- **Expected:**
  - Bot trả PNG trong < 2s.
  - Image chứa cone chart, Bé Tiền mascot, watermark.
  - **KHÔNG** chứa số tiền tuyệt đối anywhere.
  - Image size ~ 1080x1080, kích thước file < 500KB.
- **Pass:** ⏸️

### TC-019: Shareable image no auto-share prompt

- **Type:** manual
- **Story:** P4.1-B1
- **Persona:** Hà
- **Preconditions:** Tương tự TC-018.
- **Steps:**
  1. Hà bấm "📸 Lưu thành ảnh".
- **Expected:**
  - Caption đi kèm image: "Hình Twin của bạn nè, lưu giữ làm kỷ niệm 💚" (hoặc tương tự).
  - **KHÔNG** có CTA "Share lên FB", "Khoe bạn bè", "Đăng Zalo".
- **Pass:** ⏸️

### TC-020: Predictions vs actual — < 3 snapshot ẩn

- **Type:** integration
- **Story:** P4.1-B2
- **Persona:** Em Khôi
- **Preconditions:** Em Khôi có 2 snapshot completed (< 3).
- **Steps:**
  1. Em Khôi mở Twin view.
- **Expected:**
  - Section "🎯 Bé Tiền đoán đúng bao nhiêu?" KHÔNG hiển thị.
  - User flow không bị break.
- **Pass:** ⏸️

### TC-021: Predictions vs actual — hit rate honest

- **Type:** integration
- **Story:** P4.1-B2
- **Persona:** Anh Phương (backfill có 9 snapshot, 7 within band)
- **Preconditions:** Run `twin_calibration_backfill.py --user_id=anh_phuong_uuid` đầy đủ.
- **Steps:**
  1. Anh Phương mở Twin view.
- **Expected:**
  - Section "🎯 Bé Tiền đoán đúng bao nhiêu?" hiện "7/9 lần (78%)".
  - Tone neutral, không khoe khoang.
- **Pass:** ⏸️

### TC-022: Predictions vs actual — low hit rate disclaimer

- **Type:** integration
- **Story:** P4.1-B2
- **Persona:** Chị Hằng (giả định backfill cho hit rate 2/5 = 40%)
- **Preconditions:** Snapshot data setup.
- **Steps:**
  1. Chị Hằng mở Twin view.
- **Expected:**
  - Section hiện "2/5 lần (40%)" + thêm dòng "dự phóng chưa chuẩn, Bé Tiền đang học thêm 🌱".
  - KHÔNG ẩn số hoặc đẩy sang số tốt hơn.
- **Pass:** ⏸️

---

## Epic C — Soft Launch Playbook

### TC-023: Invite link generation + signup tracking

- **Type:** e2e
- **Story:** P4.1-C1
- **Persona:** Mới + Operator
- **Preconditions:** Staging clean.
- **Steps:**
  1. Operator chạy `python scripts/soft_launch_acquisition.py generate --source vn_finance_community --count 5`.
  2. Operator copy 1 token, share link `t.me/BeTienBotStaging?start=invite_<token>` cho persona Mới.
  3. Persona Mới mở link, qua onboarding.
  4. Operator gõ `/cohort_stats`.
- **Expected:**
  - CSV được generate với 5 token unique.
  - Persona Mới sau onboarding có `users.acquisition_source = 'vn_finance_community'`.
  - `/cohort_stats` hiển thị "vn_finance_community: 1 signup".
- **Pass:** ⏸️

### TC-024: Invite token reuse rejected

- **Type:** integration
- **Story:** P4.1-C1
- **Persona:** Mới
- **Preconditions:** 1 token đã `used`.
- **Steps:**
  1. Account khác mở link với token đó.
- **Expected:**
  - User vẫn được start (không block flow).
  - `acquisition_source = 'organic'` thay vì source của token.
- **Pass:** ⏸️

### TC-025: Success metrics SQL queries runnable

- **Type:** unit
- **Story:** P4.1-C2
- **Persona:** N/A
- **Preconditions:** `success-metrics.md` committed.
- **Steps:**
  1. Run từng SQL query trong `success-metrics.md` trên staging DB.
- **Expected:**
  - Mỗi query execute không error.
  - Result có shape rõ ràng (single number hoặc table).
- **Pass:** ⏸️

### TC-026: Kill criteria doc completeness

- **Type:** manual
- **Story:** P4.1-C3
- **Persona:** N/A (review)
- **Preconditions:** `kill-criteria.md` committed.
- **Steps:**
  1. Operator + dev đọc cùng nhau, check từng tiêu chí.
- **Expected:**
  - Mỗi tiêu chí có: threshold số cụ thể, owner, action plan, measurement method.
  - Timeline T+7/T+14/T+28 có rõ ai làm gì khi nào.
- **Pass:** ⏸️

---

## End-to-End Soft Launch Smoke Test

### TC-027: Full first-session journey (operator dogfood)

- **Type:** e2e + manual
- **Story:** A.1 + A.2 + A.3 + A.5
- **Persona:** Operator (account test mới)
- **Preconditions:** Staging deploy full Phase 4.1. Sentry/budget/cost log live.
- **Steps:**
  1. Account mới `/start` → onboard với 1 asset thật.
  2. Đợi Twin compute.
  3. Bấm "📸 Lưu thành ảnh".
  4. Trigger 1 intent câu hỏi (cost ~50 VND).
  5. Check Sentry → no exception.
  6. Check `llm_cost_log` → có entry.
  7. Check `users.acquisition_source` → có value.
- **Expected:**
  - Toàn bộ flow < 7 phút.
  - Không có error nào hiển thị cho user.
  - Tất cả side-effects (cost log, intent log, Sentry) ghi nhận đúng.
- **Pass:** ⏸️

### TC-028: Operator daily morning routine

- **Type:** manual
- **Story:** A.4 + A.6 + A.7
- **Persona:** Operator
- **Preconditions:** Đã có 1 ngày staging traffic.
- **Steps:**
  1. 8:00 ICT — đọc KPI digest.
  2. Gõ `/feedback_inbox` xem có feedback nào pending.
  3. Reply ít nhất 1 feedback.
- **Expected:**
  - Routine hoàn tất trong < 15 phút.
  - Operator có thông tin đủ để quyết định "hôm nay cần fix gì".
- **Pass:** ⏸️

---

## Sign-Off

| Tester | Role | Test Cases Covered | Date | Signature |
|---|---|---|---|---|
| | Operator/Founder | TC-001 to TC-028 | | |
| | Dev lead | A.3, A.5, A.6, B.1, B.2 integration | | |
| | Trusted user 1 | TC-001, TC-002, TC-014, TC-018 | | |
| | Trusted user 2 | TC-001, TC-002, TC-014, TC-018 | | |

**Soft launch GO/NO-GO decision:**
- [ ] All TC pass ≥ 95% (allow ≤ 2 partial).
- [ ] No critical bug (P1) unresolved.
- [ ] Cost guardrail tested với real LLM call.
- [ ] Sentry receiving events đủ 24h.
- [ ] 50 invite link generated + distributed.

**Decision date:** _______________ **Result:** GO / NO-GO

---

<!-- Sau khi tất cả tester sign + decision GO, đổi marker đầu file thành:
testing-signoff: signed
để trigger archive workflow. -->
