# Phase 4.2 — GitHub Issues

> Source-of-truth cho OpenClaw PM Agent generate GitHub Issues qua Actions sync.
> Format: Epic-as-parent / Story-as-child với **numbered Epics** (Epic 1, 2, 3 — convention từ Phase 4.2 trở đi).
> Labels chuẩn: `phase-4.2`, `epic-1|2|3`, `story`, `epic`, plus area labels (`area-trust`, `area-data-quality`, `area-activation`, `area-positioning`).

---

## EPIC #1: Trust & Data Integrity

**Type:** Epic
**Labels:** `phase-4.2`, `epic-1`, `epic`, `priority-p0`
**Estimate:** ~2.5 ngày (2 stories)

### Description

Đảm bảo user mới có moment xử lý câu hỏi *"Tôi có nên nhập tài sản thật?"* + đảm bảo input data sạch trước khi feed Twin engine. Đây là foundation cho mọi feature sau đó — nếu user không trust hoặc data garbage, mọi engineering polish của Phase 4.1 vô ích.

### Goals

- User thấy trust signal trước khi nhập tài sản → trust_acceptance_rate ≥ 90%
- Bad data input được catch sớm (số quá nhỏ/quá lớn, format ambiguous, duplicate)
- Placeholder asset không bị mix với real asset trong analytics

### Child Stories

- #1.1 Trust & Privacy Moment
- #1.2 Financial Data Quality Guardrails

### Definition of Done

- Trust funnel E2E test pass
- Confirm step pattern handles 9 edge cases (xem test cases)
- Migration 4.2.01 + 4.2.02 applied dev + staging
- Backfill placeholder cho 50tr demo asset trong DB hiện tại

---

## STORY #1.1: Trust & Privacy Moment

**Type:** Story
**Parent:** EPIC #1 (Trust & Data Integrity)
**Labels:** `phase-4.2`, `epic-1`, `story`, `area-trust`, `priority-p0`
**Estimate:** 0.5 ngày

### Description

Insert trust card sau Step 1 (goal question) và trước Step 2 (asset input) trong onboarding flow. User phải bấm "OK, tiếp tục" hoặc "Tôi có câu hỏi" trước khi nhập tài sản.

### Layer

- `bot/handlers/start_handler.py` (extend)
- `services/onboarding/trust_service.py` (new)
- `services/onboarding/onboarding_service.py` (extend: trust state transition)
- `content/onboarding/trust_card.yaml` (new)

### Acceptance Criteria

- [ ] Trust card hiển thị **giữa Step 1 và Step 2** khi `trust_accepted_at IS NULL`
- [ ] Welcome message (Phase 4.1) thêm 1 dòng nhẹ: *"...dữ liệu của bạn chỉ ở đây với bạn"*
- [ ] Trust card content match `trust_card.yaml`:
  - 3 bullet về privacy + edit/delete option + disclaimer
  - 2 inline button: "✅ OK, tiếp tục" / "❓ Tôi có câu hỏi"
- [ ] **"OK, tiếp tục"** → `trust_accepted_at = NOW()`, advance state đến `first_asset`
- [ ] **"Tôi có câu hỏi"** → `trust_question_raised_at = NOW()`:
  - Bot phản hồi prompt user gõ câu hỏi tự do
  - Tạo `feedbacks` record với `category='pre_onboarding_question'`, `priority='high'`
  - Sau khi user gõ xong, bot acknowledge và quay lại trust card với option "OK, tiếp tục"
  - Không loop infinite: chỉ 1 lần question allowed
- [ ] Trust card chỉ hiển thị 1 lần per user (skip nếu `trust_accepted_at IS NOT NULL`)
- [ ] Feature flag `TRUST_CARD_ENABLED` (default ON)
- [ ] Metric tracked: `trust_acceptance_rate = trust_accepted / trust_shown` (target ≥ 90%)
- [ ] Toàn bộ string trong yaml, không hardcode
- [ ] `vi-localization-checker` pass

### Tone Discipline

- KHÔNG legalistic, KHÔNG hype, KHÔNG condescending
- Tone: factual, brief, human

### Dependencies

- Depends on: Migration `4.2.02` (onboarding_sessions extended columns)
- Blocks: nothing (parallel with 1.2 OK)

---

## STORY #1.2: Financial Data Quality Guardrails

**Type:** Story
**Parent:** EPIC #1
**Labels:** `phase-4.2`, `epic-1`, `story`, `area-data-quality`, `priority-p0`
**Estimate:** 2 ngày

### Description

Hardening data input pipeline cho asset entry. Bao gồm: amount validation, confirm step với 3-option pattern, currency disambiguation, asset class clarity, placeholder isolation, duplicate detection.

### Layer

- `services/asset/asset_validation_service.py` (new — pure function)
- `services/asset/asset_confirm_service.py` (new)
- `services/asset/asset_duplicate_service.py` (new)
- `bot/handlers/asset_handler.py` (extend)
- `content/onboarding/asset_confirm.yaml` (new)
- KPI digest update (extend Phase 4.1 A.6)

### Acceptance Criteria

**Validation rules:**
- [ ] Amount < 10,000 VND → trigger confirm step
- [ ] Amount > 100 tỷ VND → trigger confirm step
- [ ] Format ambiguous (số không có đơn vị) → trigger disambiguation

**Confirm step pattern:**
- [ ] Khi user gõ "500": bot show 3 button với giá trị cụ thể (500.000đ / 500.000.000đ / 500.000.000.000đ) + escape
- [ ] Default ordering: dựa wealth segment user (nếu có history)
- [ ] Escape → quay lại prompt
- [ ] Asset save với `is_confirmed=TRUE` SAU khi confirm; pending save với `is_confirmed=FALSE`
- [ ] `source_input_raw` lưu string gốc

**Currency disambiguation:**
- [ ] Nếu amount < 10tr VND VÀ segment ≠ starter → confirm VND vs USD (2 button)

**Asset class clarity:**
- [ ] User gõ "5 căn nhà" / "1000 cổ phiếu MWG" → bot detect non-amount → prompt giá trị ước tính
- [ ] Save `source_input_raw` cho debug

**Placeholder isolation:**
- [ ] 50tr demo asset từ Phase 4.1 → `is_placeholder_asset=TRUE`
- [ ] Migration 4.2.01 backfill existing placeholder với heuristic + dry-run
- [ ] All net worth computations exclude `is_placeholder_asset=TRUE`
- [ ] Phase 4.1 metric C.2 "% user log real asset" updated filter

**Duplicate detection:**
- [ ] Cùng user + asset_type + amount ±10% trong 10 phút → flag duplicate
- [ ] Bot prompt confirm với 2 button override
- [ ] Override → insert với `data_quality_warning_type='duplicate_detected_overridden'`

**KPI digest extension:**
- [ ] Daily KPI digest thêm dòng `data_quality_warning_count` breakdown
- [ ] 🚨 flag nếu warning > 10/ngày

**Editorial:**
- [ ] Tất cả disambiguation copy không blame user
- [ ] User vô tội, Bé Tiền clarify

### Technical Notes

- `asset_validation_service` là pure function (no DB) — return validation result
- `asset_confirm_service` lưu pending asset với `is_confirmed=FALSE` cho audit
- `asset_duplicate_service` query với window `created_at > NOW() - INTERVAL '10 minutes'`
- Migration `4.2.01` có dry-run mode cho backfill

### Dependencies

- Depends on: Migration `4.2.01`
- Blocks: 2.1 (Next Best Action logic phụ thuộc real-vs-placeholder distinction)

---

## EPIC #2: Activation & Engagement

**Type:** Epic
**Labels:** `phase-4.2`, `epic-2`, `epic`, `priority-p0`
**Estimate:** ~2 ngày (3 stories)

### Description

Dẫn user từ "thấy Twin" sang "hành động cụ thể" — đây là activation thật, không phải view-only. Soft-introduce query-first habit để user dần chuyển sang gõ thay vì bấm sau Day 7. Đảm bảo briefing #1 không boring (habit-forming Day 2).

### Goals

- ≥ 60% user thực hiện next action trong 24h sau Twin
- ≥ 30% user gõ query tự do trong 7 ngày đầu (vs 100% click button)
- 100% briefing #1 có ít nhất 1 personalized insight

### Child Stories

- #2.1 Next Best Action: 9-CTA matrix
- #2.2 First briefing content quality bar
- #2.3 Query-first soft prompts

---

## STORY #2.1: Next Best Action — 9-CTA Matrix

**Type:** Story
**Parent:** EPIC #2
**Labels:** `phase-4.2`, `epic-2`, `story`, `area-activation`, `priority-p0`
**Estimate:** 1 ngày

### Description

Sau khi user thấy Twin và bấm feedback emoji (Phase 4.1 A.2), insert personalized CTA dựa trên matrix 3 asset states × 3 goals = 9 unique CTA. Track activation metric.

### Layer

- `services/onboarding/next_action_service.py` (new — pure function)
- `bot/handlers/onboarding_handler.py` (extend)
- `content/onboarding/next_action.yaml` (new — 9 CTA strings)

### Acceptance Criteria

- [ ] CTA insert SAU emoji feedback message, TRƯỚC "Sáng mai 8h..." message
- [ ] `next_action_service.compute(user_id)` return CTA dựa matrix 3×3:
  - Asset state: `demo` | `real_no_income` | `real_with_income`
  - Goal: `understand_wealth` | `plan_goal` | `track_spending`
  - 9 unique CTA strings trong yaml
- [ ] CTA render format:
  - Prefix: `💡 Bước tiếp theo dành cho bạn:`
  - CTA text từ matrix
  - Inline button shortcut (vd: "🌱 Thêm tài sản")
  - Soft prompt cuối: *"...hoặc hỏi Bé Tiền bất cứ điều gì về Twin"* (query-first hook)
- [ ] Logic detect:
  - `real_asset` = ít nhất 1 row WHERE `is_placeholder_asset=FALSE AND is_confirmed=TRUE`
  - `has_income` = ít nhất 1 row trong `income_sources` (Phase 4B)
- [ ] User bấm button shortcut → log `next_best_action_taken` + `next_best_action_at`
- [ ] User gõ query tự do thay vì bấm → log `next_best_action_taken='asked_query'`
- [ ] Recompute CTA mỗi lần user mở `/menu` hoặc Twin view (state changes → CTA changes)
- [ ] Toàn bộ 9 CTA trong yaml, không hardcode

### Metric

- Target: `next_best_action_taken IS NOT NULL` ≥ 60% trong 24h sau Twin
- Track distribution của 6 action types (added_real_asset, added_income, set_goal, logged_expense, asked_query, none)

### Dependencies

- Depends on: 1.2 (placeholder distinction logic)
- Depends on: Phase 4.1 A.2 (emoji feedback flow)

---

## STORY #2.2: First Briefing Content Quality Bar

**Type:** Story
**Parent:** EPIC #2
**Labels:** `phase-4.2`, `epic-2`, `story`, `area-activation`, `area-briefing`, `priority-p1`
**Estimate:** 0.5 ngày

### Description

Đảm bảo first briefing (Phase 4.1 A.8) chứa ít nhất 1 personalized insight, không phải template generic. Editorial discipline cho briefing content.

### Layer

- `services/briefing/briefing_content_quality_service.py` (new)
- `content/briefing/content_quality_templates.yaml` (new)
- Extend Phase 4.1 A.8 first briefing flow

### Acceptance Criteria

- [ ] Service `compute_insight(user)` return personalized insight dựa user state + segment
- [ ] Template trong yaml với fields:
  - `trigger_condition` (SQL-like rule)
  - `insight_text` (Vietnamese, < 200 chars)
  - `suggested_query` (follow-up gợi ý)
- [ ] Ít nhất 5 template ban đầu cover các case phổ biến:
  - young_pro với 100% cash
  - mass_affluent với 1 asset class duy nhất
  - track_spending goal nhưng chưa có expense logs
  - hnw với portfolio cụ thể
  - starter mới bắt đầu (encouragement)
- [ ] Fallback template: chung về segment + "Bé Tiền đang học pattern của bạn"
- [ ] Editorial: mỗi insight có ít nhất 1 trong: so sánh segment, suggest action, pose câu hỏi
- [ ] LLM personalization (nếu cần) qua `cost_tracking_adapter` từ Phase 4.1 A.3
- [ ] **Operator manual review 5 briefing #1 đầu tiên** của founding member trong tuần
- [ ] Disclaimer: "Bé Tiền nhận thấy..." thay vì "Bạn nên..." (tránh tự tin sai)

### Dependencies

- Depends on: Phase 4.1 A.8 (first briefing infrastructure)

---

## STORY #2.3: Query-First Soft Prompts

**Type:** Story
**Parent:** EPIC #2
**Labels:** `phase-4.2`, `epic-2`, `story`, `area-activation`, `content-only`, `priority-p1`
**Estimate:** 0.5 ngày

### Description

Edit content yaml để add soft prompts khuyến khích user gõ query thay vì chỉ bấm button. Không touch code logic.

### Layer

- `content/onboarding/welcome_v2.yaml` (extend)
- `content/onboarding/first_twin_intro.yaml` (extend)
- `content/onboarding/first_briefing.yaml` (extend)
- `content/onboarding/next_action.yaml` (from Story 2.1)

### Acceptance Criteria

- [ ] Welcome message: thêm cuối *"💬 Bạn cũng có thể gõ câu hỏi bất cứ lúc nào — Bé Tiền hiểu tiếng Việt"*
- [ ] Twin reveal message 3: thêm cuối *"💬 Có câu hỏi về Twin? Cứ hỏi Bé Tiền nhé"*
- [ ] First briefing: thêm *"Hoặc hỏi cụ thể — vd: 'sao tài sản của tôi giảm?'"*
- [ ] Next Best Action CTA: thêm *"...hoặc hỏi Bé Tiền bất cứ điều gì về Twin"*
- [ ] Mỗi prompt < 100 chars
- [ ] Không lặp lại tone "bạn có thể..." quá nhiều
- [ ] Track metric: `entry_mode='query'` vs `'button'` trong `intent_logs` (track existing column hoặc add)
- [ ] Target: ≥ 30% user dùng query trong 7 ngày đầu

### Technical Notes

- Pure content edit, no code logic change
- Có thể merge cùng PR với Story 2.1

### Dependencies

- Depends on: 2.1 (next_action.yaml created)

---

## EPIC #3: Positioning Validation

**Type:** Epic
**Labels:** `phase-4.2`, `epic-3`, `epic`, `priority-p1`
**Estimate:** ~0.5 ngày (2 stories)

### Description

Verify user thật sự hiểu Bé Tiền là Personal CFO (không phải expense tracker). Survey + kill criterion + discipline trước scale.

### Goals

- ≥ 60% user chọn đúng positioning trong Day 7 survey
- Kill criterion documented và actionable
- Acquisition expansion gated bởi positioning health

### Child Stories

- #3.1 Day 7 Positioning Micro-Survey
- #3.2 Positioning Misalignment Kill Criterion

---

## STORY #3.1: Day 7 Positioning Micro-Survey

**Type:** Story
**Parent:** EPIC #3
**Labels:** `phase-4.2`, `epic-3`, `story`, `area-positioning`, `priority-p1`
**Estimate:** 0.25 ngày

### Description

Thêm 1 câu survey vào cuối Day 7 follow-up message (đã có trong Phase 4.1 deploy-announcements). 4 option chọn nhanh.

### Layer

- `services/survey/positioning_survey_service.py` (new)
- `content/survey/positioning_survey.yaml` (new)
- Extend Day 7 follow-up message handler

### Acceptance Criteria

- [ ] Day 7 message thêm survey:
  > 💭 Bé Tiền tò mò 1 chút — sau 7 ngày dùng thử, bạn thấy Bé Tiền giống nhất với gì?
  >
  > [📊 App quản lý chi tiêu]
  > [🤖 Trợ lý tài chính cá nhân]
  > [🔮 Công cụ nhìn tương lai tài chính]
  > [🤔 Chưa hiểu rõ]
- [ ] User bấm → insert `positioning_survey_responses` row
- [ ] UNIQUE constraint trên `user_id` — chỉ survey 1 lần
- [ ] Acknowledge: *"Cảm ơn bạn — giúp Bé Tiền hiểu rõ mình hơn 💚"*
- [ ] Weekly KPI digest có section mới "Positioning":
  - % chọn mỗi option
  - Target: ≥ 60% chọn option 2 hoặc 3
  - Alert nếu > 30% chọn option 1 hoặc 4

### Dependencies

- Depends on: Migration `4.2.03`

---

## STORY #3.2: Positioning Misalignment Kill Criterion

**Type:** Story
**Parent:** EPIC #3
**Labels:** `phase-4.2`, `epic-3`, `story`, `area-positioning`, `docs-only`, `priority-p1`
**Estimate:** 0.25 ngày

### Description

Document tiêu chí dừng/redesign nếu positioning sai. Update kill-criteria.md từ Phase 4.1.

### Output

Extend `docs/current/phase-4.1/kill-criteria.md`

### Acceptance Criteria

- [ ] Thêm criterion mới:
  - **Positioning misalignment > 30%** = % user chọn option 1 hoặc 4 trong Day 7 survey
  - **Action:** Freeze acquisition, redesign welcome + Twin narrative + briefing intro trong 2 tuần, re-run với cohort 20 mới
  - **Owner:** Founder/PM
  - **Threshold trigger:** từ tuần thứ 2 sau Phase 4.2 launch (cần ≥ 20 response)
- [ ] Update table-of-contents trong kill-criteria.md

### Dependencies

- Depends on: 3.1 (survey infrastructure)

---

## INFRA / MIGRATION TASKS

### TASK #M.1: Migration `4.2.01_asset_quality_flags`

**Type:** Task
**Labels:** `phase-4.2`, `infra`, `migration`, `priority-p0`
**Estimate:** 0.25 ngày

- [ ] ALTER `assets` table: thêm `is_placeholder_asset`, `is_confirmed`, `source_input_raw`, `data_quality_warning_at`, `data_quality_warning_type`
- [ ] Create partial indexes: `idx_assets_real`, `idx_assets_recent`
- [ ] **Backfill script với dry-run mode** cho 50tr placeholder cũ
- [ ] Operator review 5-10 candidate trước commit thật
- [ ] Apply dev + staging

### TASK #M.2: Migration `4.2.02_onboarding_trust_state`

**Type:** Task
**Labels:** `phase-4.2`, `infra`, `migration`, `priority-p0`
**Estimate:** 0.1 ngày

- [ ] ALTER `onboarding_sessions`: thêm `trust_shown_at`, `trust_accepted_at`, `trust_question_raised_at`, `next_best_action_taken`, `next_best_action_at`
- [ ] Apply dev + staging

### TASK #M.3: Migration `4.2.03_positioning_survey`

**Type:** Task
**Labels:** `phase-4.2`, `infra`, `migration`, `priority-p1`
**Estimate:** 0.1 ngày

- [ ] CREATE TABLE `positioning_survey_responses` với UNIQUE(user_id)
- [ ] Create index `idx_positioning_survey_response`
- [ ] Apply dev + staging

---

## DEPLOY READINESS TASKS

### TASK #D.1: Editorial Discipline Doc cho Operator

**Type:** Task
**Labels:** `phase-4.2`, `docs`, `priority-p0`
**Estimate:** 0.25 ngày

- [ ] Tạo `docs/current/phase-4.2/operator-editorial-discipline.md`
- [ ] Rule: không reference số tiền cụ thể trong feedback reply
- [ ] Vd: ❌ "tôi thấy bạn có 1.5 tỷ" → ✅ "với portfolio của bạn..."
- [ ] Checklist cho operator daily check-in: *"Tôi có reference số tiền cụ thể không?"*
- [ ] Reference trong trust card commitment

### TASK #D.2: Content Quality Playbook

**Type:** Task
**Labels:** `phase-4.2`, `docs`, `priority-p1`
**Estimate:** 0.25 ngày

- [ ] Tạo `docs/current/phase-4.2/content-quality-playbook.md`
- [ ] Editorial rules cho briefing content (so sánh segment / suggest action / pose câu hỏi)
- [ ] Operator review checklist cho briefing #1
- [ ] Pattern library với 5 template ban đầu

### TASK #D.3: Manual Review Briefing #1 (Soft Launch Cohort)

**Type:** Task
**Labels:** `phase-4.2`, `deploy`, `priority-p0`
**Estimate:** 0.5 ngày (over 1 week)

- [ ] Operator đọc 5 briefing #1 đầu của founding member
- [ ] Verify: ít nhất 1 personalized insight
- [ ] Verify: editorial discipline (không "Bạn nên...")
- [ ] Document edge cases vào content quality playbook
- [ ] Fix template/prompt nếu boring

---

## SUMMARY

| Type | Count | Total Estimate |
|---|---|---|
| Epics | 3 | — |
| Stories | 7 | ~5 ngày |
| Migration tasks | 3 | ~0.45 ngày |
| Deploy tasks | 3 | ~1 ngày |
| **Total** | **16 issues** | **~6.5 ngày (~2 tuần với buffer)** |

### Critical Path

```
#M.1 → #1.2 (data quality) ──┐
#M.2 → #1.1 (trust) ─────────┤
                              ├── #2.1 (next best action)
                              │       │
                              │       ├── #2.2 (briefing quality)
                              │       └── #2.3 (query-first prompts)
                              │
#M.3 → #3.1 (survey) ─── #3.2 (kill criterion update)
                              
                              ↓
                          Soft launch continuation (50→100)
```

### Recommendation

Ship Story #1.2 (Data Quality) trước #1.1 (Trust) — vì data quality là foundation cho mọi metric. Trust card có thể delay vài ngày nếu cần.

**Ship 2.2 (Briefing quality) sớm nhất trong Epic 2** — vì founding member đang active, briefing #1 boring = churn signal sớm.
