# Phase 4.2 — Customer Experience Hardening

> **Prerequisites:** Phase 4.1 đã deployed và stable trên production. Soft launch 50 user đã đang chạy hoặc đã xong.
> **Thời gian:** ~2 tuần (~7-8 ngày work + buffer testing).
> **Mục tiêu:** Bridge gap từ "engineering-ready" (đã đạt với 4.1) sang "customer-experience-ready". Phase 4.1 đảm bảo hệ thống chạy ổn — Phase 4.2 đảm bảo user mới **thật sự muốn ở lại**.
> **"Done":** Trust signal trong onboarding rõ ràng, data input quality cao (false-positive Twin < 5%), activation rate (user thực hiện next action sau Twin) ≥ 60%, positioning misalignment < 30% qua Day 7 survey.
> **Convention change:** từ Phase 4.2 trở đi, Epic dùng numbered convention (Epic 1, 2, 3...) thay vì lettered (Epic A, B, C).

Phase 4.2 ra đời từ **retrospective sau Phase 4.1**. Khi đọc lại Phase 4.1 detailed, nhận ra một sự thật khó chịu: Phase 4.1 nghiêng quá về engineering readiness (Sentry, budget cap, feedback inbox, KPI digest) trong khi **vẫn để hở 5 lỗ hổng customer-experience** cụ thể:

1. **Không có "trust moment"** trước khi user nhập tài sản thật — user mass affluent VN ngại nhập số thật vào bot lạ.
2. **Không có "next best action" sau Twin** — wow moment kết thúc bằng dashboard, không phải hành động cụ thể.
3. **Không có data quality guardrails** — user có thể nhập 500 thay vì 500 triệu, Twin sai → trust mất.
4. **Không có positioning validation** — không biết user có hiểu Bé Tiền là Personal CFO hay nhầm thành expense tracker.
5. **UI hơi nặng menu-first** — Phase 3.5 đầu tư vào intent classification nhưng onboarding/Twin views chủ yếu inline button → user không học query-first habit.

Phase 4.2 đóng 5 lỗ hổng này thành 7 story trong 3 Epic. Đây là phase ngắn (2 tuần) nhưng có impact cao trên activation rate và D7/D30 retention.

---

## 🎯 Triết Lý Thiết Kế Phase 4.2

### 1. Trust is foundation, not feature

Trust không phải là 1 tính năng để add — nó là điều kiện cần trước khi mọi feature khác có giá trị. User không trust = không nhập data thật = mọi engineering work của Phase 4.1 trở thành thừa.

### 2. Bad data is worse than no data

Twin của user nhập sai số tiền (500 thay vì 500tr) còn nguy hiểm hơn user chưa nhập gì. Hơn nữa, bad data **silent** — user không biết Bé Tiền parse sai → chỉ thấy Twin kỳ lạ → mute. Data quality phải hardening **trước** mọi computation downstream.

### 3. Wow without action = wow without retention

Phase 4.1 đo TTFT (time-to-first-Twin) — đạt < 5 phút. Nhưng "thấy Twin" không phải activation thật. **Activation thật = user làm 1 hành động sau khi thấy Twin** — thêm asset, thêm income, đặt goal, hoặc hỏi Bé Tiền. Không có action = user chỉ là viewer, không phải user.

### 4. Positioning is testable, not assumed

Bé Tiền **muốn** là Personal CFO. Nhưng user **nghĩ** Bé Tiền là gì là câu hỏi empirical, không phải intention. Phase 4.2 đo positioning rõ ràng để nếu sai → fix copy trước khi scale.

### 5. Query-first as the long-term affordance

Soft prompts khuyến khích user gõ thay vì bấm — không phải để loại bỏ menu, mà để user **tự nhiên** chuyển sang query-first sau Day 7. Đây là how Bé Tiền's intent classification value mới thực sự được khai thác.

### 6. Continuity với Phase 4.1, không replace

Phase 4.2 KHÔNG sửa Phase 4.1. Mọi story đều là **extension hoặc insertion** vào flow đã có. Tránh re-work code đã stable.

### 7. Operator editorial discipline (internal)

Trust copy promise *"Chỉ bạn thấy chi tiết tài sản — không user nào khác nhìn được"* là true với user khác — nhưng founder/operator hiện tại có thể query DB. Để promise đó không thành nói dối tinh tế, operator có **editorial discipline** (internal-only, không expose user): không reference cụ thể số tiền user khi reply feedback. Vd: thay vì *"tôi thấy bạn có 1.5 tỷ"*, nói *"với portfolio của bạn..."*. Discipline này áp dụng cho đến khi encryption end-to-end ship trong Phase 5.

---

## 📅 Phân Bổ Thời Gian

| Tuần | Trọng tâm | Output chính |
|---|---|---|
| **Tuần 1 (~4 ngày)** | Epic 1 — Trust & Data Integrity | Trust card trước Step 2, data validation + confirm step, placeholder isolation, duplicate detection |
| **Tuần 2 (~4 ngày)** | Epic 2 + Epic 3 — Activation + Positioning | 4-case Next Best Action CTA, first briefing content quality bar, query-first soft prompts, Day 7 positioning survey, kill criterion update |

### Critical path

```
1.2 Data Quality ── 1.1 Trust Moment ── 2.1 Next Best Action ── 2.2 Briefing content quality
                                            │
                                            └── 2.3 Query-first prompts (parallel)
                                                    │
                                                    └── 3.1 Positioning survey ── 3.2 Kill criterion update
```

**Foundation:** Story 1.2 (Data Quality) phải ship đầu — vì A.2 từ Phase 4.1 (Twin trigger) đang giả định data sạch, mà thực tế chưa có guardrail.

---

## 🗂️ Cấu Trúc Thay Đổi

```
bot/handlers/
├── start_handler.py                          (extend: insert trust card before Step 2)
├── onboarding_handler.py                     (extend: 4-case next-best-action dispatch)
├── asset_handler.py                          (extend: confirm step + duplicate detection)
└── feedback_handler.py                       (extend: pre_onboarding_question tag)

services/
├── onboarding/
│   ├── onboarding_service.py                 (extend: trust card state, next_action computation)
│   ├── trust_service.py                      (new: trust card rendering, accept/question routing)
│   └── next_action_service.py                (new: 4-case CTA matrix logic)
├── asset/
│   ├── asset_validation_service.py           (new: amount validation, currency disambiguation)
│   ├── asset_confirm_service.py              (new: confirm step pattern)
│   └── asset_duplicate_service.py            (new: 10-min window duplicate detection)
├── briefing/
│   └── briefing_content_quality_service.py   (new: personalized insight bar)
└── survey/
    └── positioning_survey_service.py         (new: Day 7 survey + result aggregation)

content/
├── onboarding/
│   ├── trust_card.yaml                       (new: trust copy + question button)
│   ├── next_action.yaml                      (new: 12 CTA strings — 4 asset states × 3 goals... wait, actually 2×3 = 6 unique, 4-state is 2-asset-states. Will clarify in Story 2.1)
│   └── query_first_prompts.yaml              (new: soft prompts)
├── briefing/
│   └── content_quality_templates.yaml        (new: personalized insight templates)
└── survey/
    └── positioning_survey.yaml               (new: Day 7 question + 4 options)

alembic/versions/
├── 4.2.01_asset_quality_flags.py             (new: is_placeholder, is_confirmed, source_input_raw)
├── 4.2.02_onboarding_trust_state.py          (new: extend onboarding_sessions)
└── 4.2.03_positioning_survey.py              (new: positioning_survey_responses table)

docs/current/phase-4.2/
├── phase-4.2-detailed.md                     (this file)
├── phase-4.2-issues.md
├── phase-4.2-test-cases.md
├── phase-4.2-deploy-announcements.md
└── content-quality-playbook.md               (new: editorial discipline cho briefing content)
```

---

## 🗄️ Database Schema

### Migration `4.2.01_asset_quality_flags.py`

```sql
ALTER TABLE assets
    ADD COLUMN is_placeholder_asset BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN is_confirmed BOOLEAN NOT NULL DEFAULT TRUE,    -- TRUE cho asset đã qua confirm step
    ADD COLUMN source_input_raw TEXT NULL,                    -- string gốc user gõ ("500", "1 tỷ")
    ADD COLUMN data_quality_warning_at TIMESTAMPTZ NULL,      -- khi nào trigger warning
    ADD COLUMN data_quality_warning_type VARCHAR(32) NULL;    -- 'too_small' | 'too_large' | 'ambiguous_format' | 'duplicate_detected'

-- Backfill existing placeholder (50tr demo từ Phase 4.1 Story A.1)
UPDATE assets
SET is_placeholder_asset = TRUE
WHERE amount_vnd = 50000000
  AND id IN (
    SELECT a.id FROM assets a
    JOIN onboarding_sessions os ON os.user_id = a.user_id
    WHERE os.inferred_wealth_segment IS NULL
      AND a.created_at = os.started_at + INTERVAL '5 minutes'  -- heuristic
  );

-- Partial index để query asset thật nhanh (analytics exclusion)
CREATE INDEX idx_assets_real
    ON assets(user_id, asset_type)
    WHERE is_placeholder_asset = FALSE AND is_confirmed = TRUE;

-- Index cho duplicate detection (10-min window)
CREATE INDEX idx_assets_recent
    ON assets(user_id, created_at, amount_vnd)
    WHERE created_at > NOW() - INTERVAL '1 hour';
```

**Lưu ý:**
- Backfill heuristic không hoàn hảo — operator nên review manual 5-10 placeholder candidate trước khi commit migration.
- `is_confirmed=FALSE` cho asset đang chờ user confirm trong Step 2 disambiguation flow.
- `source_input_raw` giữ string gốc → useful cho debugging "tại sao Bé Tiền parse 500 thành 500đ thay vì 500tr".

### Migration `4.2.02_onboarding_trust_state.py`

```sql
ALTER TABLE onboarding_sessions
    ADD COLUMN trust_shown_at TIMESTAMPTZ NULL,           -- khi trust card hiển thị
    ADD COLUMN trust_accepted_at TIMESTAMPTZ NULL,        -- khi user bấm "OK, tiếp tục"
    ADD COLUMN trust_question_raised_at TIMESTAMPTZ NULL, -- khi user bấm "Tôi có câu hỏi"
    ADD COLUMN next_best_action_taken VARCHAR(64) NULL,   -- 'added_real_asset' | 'added_income' | 'set_goal' | 'logged_expense' | 'asked_query' | 'none'
    ADD COLUMN next_best_action_at TIMESTAMPTZ NULL;
```

**Lưu ý:** `trust_shown_at` riêng với `trust_accepted_at` để tracking funnel drop ở trust step (user thấy trust nhưng không chấp nhận → quan trọng signal).

### Migration `4.2.03_positioning_survey.py`

```sql
CREATE TABLE positioning_survey_responses (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    response VARCHAR(64) NOT NULL,                        -- 'expense_tracker' | 'personal_assistant' | 'future_vision' | 'unclear'
    sent_at TIMESTAMPTZ NOT NULL,                         -- khi survey hiển thị
    responded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id)                                       -- chỉ survey 1 lần/user
);

CREATE INDEX idx_positioning_survey_response
    ON positioning_survey_responses(response);
```

---

## 🔧 Epic 1 — Trust & Data Integrity

**Goal:** User cảm thấy đủ tin để nhập data thật, và data nhập vào đảm bảo chất lượng để Twin computation chính xác.

**Stories:** 1.1 + 1.2 (2 stories, ~2.5 ngày)

### Story 1.1 — Trust & Privacy Moment

**Layer:** `bot/handlers/start_handler.py` (extend) + `services/onboarding/trust_service.py` (new) + `content/onboarding/trust_card.yaml` (new)

**Acceptance:**
- Trust card hiển thị **trước Step 2** (sau Step 1 goal question, trước khi prompt nhập asset). Logic: nếu `onboarding_sessions.trust_accepted_at IS NULL` AND `current_step` chuẩn bị chuyển từ `goal_question` → `first_asset`, chèn trust card.
- **Welcome message cũng có 1 dòng nhẹ** mention privacy ("...dữ liệu của bạn chỉ ở đây với bạn") — không phải full trust copy, chỉ là teaser/expectation setter.
- Trust card content (từ `trust_card.yaml`):

  ```
  🔒 Bé Tiền tôn trọng tiền bạc của bạn

  • Chỉ bạn thấy chi tiết tài sản — không user nào khác nhìn được
  • Bạn xoá hoặc sửa bất cứ lúc nào qua /profile
  • Dự phóng tương lai là tham khảo, không phải lời khuyên đầu tư

  Sẵn sàng bắt đầu chưa?

  [✅ OK, tiếp tục]  [❓ Tôi có câu hỏi]
  ```

- **Bấm "OK, tiếp tục"** → `trust_accepted_at = NOW()`, advance state đến `first_asset` (Step 2 hiện ra).
- **Bấm "Tôi có câu hỏi"** → `trust_question_raised_at = NOW()`. Bot phản hồi: *"Bé Tiền nghe bạn — gõ câu hỏi của bạn, founder Bé Tiền sẽ trả lời trong vài giờ tới."* User gõ câu hỏi → tạo `feedbacks` record với `category='pre_onboarding_question'`, `priority='high'`. Sau khi user gõ xong, bot acknowledge và quay lại trust card với option "OK, tiếp tục" (không loop infinite — chỉ 1 lần question allowed).
- **Funnel metric mới:** `trust_acceptance_rate = trust_accepted / trust_shown` — target ≥ 90%. Nếu < 90% → trust copy có vấn đề, cần iterate.
- Trust card chỉ hiển thị **1 lần** per user — nếu user `/start` lại (đã accepted trước), skip trust card.

**Tone discipline:**
- Không legalistic ("Theo Điều 5 Luật bảo vệ dữ liệu...")
- Không hype ("100% an toàn tuyệt đối")
- Không condescending ("Đừng lo, dữ liệu của bạn rất an toàn")
- Tone: factual, brief, human

### Story 1.2 — Financial Data Quality Guardrails

**Layer:** `services/asset/asset_validation_service.py` (new) + `services/asset/asset_confirm_service.py` (new) + `services/asset/asset_duplicate_service.py` (new) + `bot/handlers/asset_handler.py` (extend)

**Acceptance:**

**Validation rules:**
- Amount < 10,000 VND → trigger confirm: *"Bạn chắc ý là 10 nghìn không, hay 10 triệu / 10 tỷ?"* — 3 button lựa chọn nhanh + escape.
- Amount > 100 tỷ VND → trigger confirm: *"Số khá lớn — bạn chắc số đúng không?"* — chỉ confirm/sửa, không assume bad faith.
- Format ambiguous (vd: user gõ chỉ số "500" không có đơn vị) → trigger disambiguation step.

**Confirm step pattern (`asset_confirm_service`):**

```
User: 500
Bot: Bé Tiền chưa rõ — bạn ý là:

[💰 500.000đ (năm trăm nghìn)]
[💵 500.000.000đ (năm trăm triệu)]
[🏦 500.000.000.000đ (năm trăm tỷ)]
[✏️ Khác — nhập lại]
```

- 3 button hiển thị **giá trị cụ thể** (không phải technical "VND đúng không?") — user mass affluent sẽ nhận ra ngay số nào của mình.
- Default thông minh dựa trên wealth segment đã infer (nếu user có history) → đặt giá trị có khả năng nhất lên đầu.
- Escape "✏️ Khác" → quay lại prompt input.
- Asset chỉ insert vào `assets` với `is_confirmed=TRUE` SAU khi confirm step pass. Asset chờ confirm có thể save tạm với `is_confirmed=FALSE`.
- `source_input_raw` lưu string gốc ("500") để debug.

**Currency disambiguation:**
- Nếu amount sau parse < 10 triệu VND VÀ user segment không phải `starter` → confirm: *"Bạn ý là 5 triệu VND hay 5.000 USD (~120 triệu VND)?"* — 2 button.

**Asset class clarity:**
- User gõ "5 căn nhà" hoặc "1000 cổ phiếu MWG" → bot detect non-amount → prompt: *"Bé Tiền cần giá trị ước tính bằng tiền — bạn ước khoảng bao nhiêu?"*
- Save raw input vào `source_input_raw` để debug.

**Placeholder isolation:**
- 50tr demo asset từ Story A.1 (Phase 4.1) → set `is_placeholder_asset=TRUE` khi insert.
- Migration `4.2.01` có backfill cho existing placeholder.
- All real net worth computations exclude `is_placeholder_asset=TRUE`.
- KPI metric C.2 "% user log ≥ 1 asset thật" filter `is_placeholder_asset=FALSE AND is_confirmed=TRUE`.

**Duplicate detection:**
- Trước khi insert asset mới, query: cùng `user_id` + cùng `asset_type` + amount trong ±10% trong 10 phút gần nhất → flag duplicate.
- Bot prompt: *"Bạn đã thêm tài sản tương tự cách đây [X] phút. Đây có phải là asset mới khác không?"* — 2 button: "Có, asset mới" / "Không, xoá entry này".
- Nếu user confirm "asset mới" → insert với `data_quality_warning_type='duplicate_detected_overridden'`.

**KPI digest extension:**
- Daily KPI digest (từ Phase 4.1 Story A.6) thêm dòng: *"⚠️ Data quality warnings 24h: 3 (1 ambiguous, 1 too_large, 1 duplicate)"*
- Nếu warning count > 10/ngày → 🚨 flag (signal có thể UI/copy gây nhầm lẫn).

**Editorial:** Tất cả disambiguation copy phải short, friendly, không blame user. Mặc định: user vô tội, Bé Tiền chỉ cần clarify.

---

## 🔧 Epic 2 — Activation & Engagement

**Goal:** Sau khi user thấy Twin, dẫn họ đến hành động cụ thể (không phải "đợi briefing mai 8h"). Soft-introduce query-first habit. Đảm bảo briefing #1 không boring.

**Stories:** 2.1 + 2.2 + 2.3 (3 stories, ~2 ngày)

### Story 2.1 — Next Best Action: 6-CTA matrix (2 asset states × 3 goals)

**Layer:** `services/onboarding/next_action_service.py` (new) + `bot/handlers/onboarding_handler.py` (extend) + `content/onboarding/next_action.yaml` (new)

**Acceptance:**
- Sau khi user bấm emoji feedback (😍/🤔/😕) trong Phase 4.1 Story A.2, **trước message "Sáng mai 8h Bé Tiền gửi briefing đầu tiên"**, insert Next Best Action message.
- `next_action_service.compute(user_id)` return 1 CTA dựa trên matrix 2×3 = 6 cases:

  | Asset state | understand_wealth | plan_goal | track_spending |
  |---|---|---|---|
  | **Demo (chưa nhập thật)** | Thêm tài sản thật để Twin trở thành của bạn | Thêm tài sản thật để Bé Tiền lập kế hoạch chính xác | Thêm tài sản thật để xem chi tiêu match được không |
  | **Real asset, no income** | Thêm 1 nguồn thu nhập để dự phóng chính xác hơn | Thêm thu nhập để Bé Tiền đề xuất mục tiêu khả thi | Ghi 1 khoản chi tiêu hôm nay để bắt đầu theo dõi |
  | **Real asset + income** | Đặt 1 mục tiêu lớn (mua nhà / nghỉ hưu / quỹ dự phòng) | Tạo mục tiêu đầu tiên — Bé Tiền sẽ track | Ghi 1 khoản chi tiêu để Bé Tiền học pattern của bạn |

  **Note:** Matrix thực tế là 3×3 = 9 cases (3 asset states × 3 goals), không phải 2×3=6. Demo asset là một state riêng (chưa có real asset), "real asset, no income" và "real asset + income" là 2 state khác. Total 9 unique CTA strings trong yaml.

- Each CTA render: prefix *"💡 Bước tiếp theo dành cho bạn:"* + CTA text + inline button shortcut (vd: "🌱 Thêm tài sản") + soft prompt cuối *"...hoặc hỏi Bé Tiền bất cứ điều gì về Twin"*.
- Logic detect "real asset" = `assets` table có ít nhất 1 row WHERE `is_placeholder_asset=FALSE AND is_confirmed=TRUE` cho user_id.
- Logic detect "has income" = bảng `income_sources` (Phase 4B Cashflow v2) có row cho user_id.
- Sau Day 1, user mở `/menu` hoặc Twin view → recompute next_best_action mỗi lần (state thay đổi → CTA thay đổi).
- **Activation metric:** track `next_best_action_taken` trong `onboarding_sessions`. Target Phase 4.2: ≥ 60% user thực hiện next action trong 24h.

### Story 2.2 — First briefing content quality bar

**Layer:** `services/briefing/briefing_content_quality_service.py` (new) + `content/briefing/content_quality_templates.yaml` (new) + extend Phase 4.1 Story A.8 first briefing flow

**Acceptance:**
- First briefing (Story A.8 từ Phase 4.1) phải pass content quality bar: chứa **ít nhất 1 personalized insight**, không phải template generic.
- Service `briefing_content_quality_service.compute_insight(user)` return insight dựa trên user data + segment. Ví dụ template:
  - young_pro với 100% cash → *"Bé Tiền chú ý: bạn giữ 100% tiền mặt. Người trong segment của bạn thường đầu tư 30-50% — nếu muốn nghe ý kiến, gõ 'giải thích đầu tư'"*
  - mass_affluent với 1 asset class duy nhất → *"Bé Tiền chú ý: portfolio của bạn tập trung vào [X]. Diversification có thể giảm rủi ro — muốn nghe phân tích, gõ 'diversify'"*
  - track_spending goal nhưng chưa có expense logs → *"Bé Tiền chú ý: bạn đã thiết lập theo dõi chi tiêu nhưng chưa ghi khoản nào. Bắt đầu với 1 khoản hôm nay nhé?"*
- Template trong `content_quality_templates.yaml`, mỗi template có:
  - `trigger_condition` (SQL-like rule trên user state)
  - `insight_text` (Vietnamese, < 200 chars)
  - `suggested_query` (text user có thể gõ để follow up)
- Fallback nếu không match template nào: insight chung về wealth segment + Bé Tiền "đang học pattern của bạn — kiểm tra lại trong 1 tuần".
- **Editorial discipline:** mỗi insight phải có ít nhất 1 trong:
  - So sánh user với segment (vd: "người trong segment của bạn thường...")
  - Suggest action cụ thể (vd: "bắt đầu với 1 khoản hôm nay")
  - Pose câu hỏi để user follow up (vd: "muốn nghe ý kiến, gõ...")
- **Operator manual review** 5 briefing #1 đầu tiên của founding members trong tuần soft launch. Nếu boring/generic → fix template/prompt trước khi mở thêm.
- LLM personalization (nếu cần) PHẢI qua `cost_tracking_adapter` (Phase 4.1 A.3) — không bypass budget cap.

### Story 2.3 — Query-first soft prompts

**Layer:** Modify content yaml only — `welcome_v2.yaml`, `first_twin_intro.yaml`, `first_briefing.yaml`, `next_action.yaml`

**Acceptance:**

| Touchpoint | Hiện tại | Thêm |
|---|---|---|
| Welcome message | Chỉ button "Bắt đầu hành trình" | Cuối message: *"💬 Bạn cũng có thể gõ câu hỏi bất cứ lúc nào — Bé Tiền hiểu tiếng Việt"* |
| Twin reveal message 3 (sau feedback emoji) | 3 emoji button | Cuối: *"💬 Có câu hỏi về Twin? Cứ hỏi Bé Tiền nhé"* |
| First briefing | Button "Bé Tiền đang nói gì?" | Thêm: *"Hoặc hỏi cụ thể — vd: 'sao tài sản của tôi giảm?'"* |
| Next Best Action CTA | Button shortcut | Cuối: *"...hoặc hỏi Bé Tiền bất cứ điều gì về Twin"* |

- Tất cả thay đổi là edit yaml, không touch code logic.
- Strings ngắn (< 100 chars mỗi), không lặp lại tone "bạn có thể..." quá nhiều.
- Sau Phase 4.2, đo: **% query-first action trong 7 ngày đầu** (user gõ tự do thay vì bấm button) — track metric mới trong `intent_logs` với `entry_mode='query'` vs `'button'`.

---

## 🔧 Epic 3 — Positioning Validation

**Goal:** Verify user thật sự hiểu Bé Tiền là Personal CFO, không nhầm thành expense tracker. Có data → có kill criterion → có discipline trước khi scale.

**Stories:** 3.1 + 3.2 (2 stories, ~0.5 ngày)

### Story 3.1 — Day 7 positioning micro-survey

**Layer:** `services/survey/positioning_survey_service.py` (new) + `content/survey/positioning_survey.yaml` (new) + extend Day 7 follow-up message (deploy-announcements)

**Acceptance:**
- Day 7 follow-up message (đã có trong Phase 4.1 deploy-announcements) thêm survey 1 câu vào cuối:

  ```
  💭 Bé Tiền tò mò 1 chút — sau khi dùng thử 7 ngày, bạn thấy Bé Tiền giống nhất với gì?

  [📊 App quản lý chi tiêu]
  [🤖 Trợ lý tài chính cá nhân]
  [🔮 Công cụ nhìn tương lai tài chính]
  [🤔 Chưa hiểu rõ]
  ```

- User bấm → insert `positioning_survey_responses` row.
- Mỗi user chỉ survey 1 lần (UNIQUE constraint).
- Acknowledge sau khi bấm: *"Cảm ơn bạn — giúp Bé Tiền hiểu rõ mình hơn 💚"*.
- KPI digest weekly có section mới "Positioning":
  - % chọn mỗi option
  - Target: ≥ 60% chọn "Trợ lý tài chính cá nhân" hoặc "Công cụ nhìn tương lai" (đúng positioning Personal CFO)
  - Alert nếu > 30% chọn "App quản lý chi tiêu" hoặc "Chưa hiểu rõ" → positioning broken.

### Story 3.2 — Positioning misalignment kill criterion

**Layer:** Documentation only — extend `docs/current/phase-4.1/kill-criteria.md` (file đã có từ Phase 4.1 C.3)

**Acceptance:**
- Thêm criterion mới vào kill-criteria.md:

  > **Positioning misalignment > 30%** = % user chọn "App quản lý chi tiêu" hoặc "Chưa hiểu rõ" trong Day 7 survey vượt ngưỡng 30%.
  >
  > **Action plan:**
  > - **Freeze acquisition mở rộng** — không gửi thêm invite, không thêm cohort > 50
  > - **Redesign welcome copy + first Twin narrative + first briefing intro** trong vòng 2 tuần
  > - **Re-run survey** sau redesign với cohort mới 20 user
  > - Chỉ khi misalignment < 30% mới resume expansion
  >
  > **Owner:** Founder/PM
  > **Threshold trigger:** đo qua weekly KPI digest, áp dụng từ tuần thứ 2 sau Phase 4.2 launch (cần ít nhất 20 response để statistical signal)

- Cập nhật table-of-contents trong kill-criteria.md.

---

## 📐 Layer Mapping

| Story | Routers | Workers | Handlers | Services | Adapters |
|---|---|---|---|---|---|
| 1.1 Trust moment | — | — | `start_handler` (extend) | `trust_service` (new), `onboarding_service` (extend) | Notifier |
| 1.2 Data quality | — | — | `asset_handler` (extend) | `asset_validation_service`, `asset_confirm_service`, `asset_duplicate_service` (all new) | — |
| 2.1 Next Best Action | — | — | `onboarding_handler` (extend) | `next_action_service` (new) | — |
| 2.2 Briefing quality | — | (extend existing briefing worker) | — | `briefing_content_quality_service` (new) | (LLM via `cost_tracking_adapter`) |
| 2.3 Query-first prompts | — | — | — | — (content yaml only) | — |
| 3.1 Positioning survey | — | — | (extend Day 7 follow-up) | `positioning_survey_service` (new) | Notifier |
| 3.2 Kill criterion | — | — | — | — (docs only) | — |

**Contract checks:**
- `trust_service` không có DB commit — chỉ `flush`. State commit ở handler boundary.
- `asset_validation_service` là pure function (no DB) — return validation result, service caller xử lý.
- `asset_confirm_service` lưu pending asset với `is_confirmed=FALSE` — không xóa khi user escape, để có data audit về abandoned input.
- `next_action_service.compute()` là pure function dựa trên user state snapshot — không gọi LLM, không có DB write.
- `briefing_content_quality_service` có thể gọi LLM (DeepSeek) để personalize, nhưng PHẢI qua `cost_tracking_adapter` (từ Phase 4.1 A.3) — không bypass budget cap.
- Toàn bộ Vietnamese string trong `content/*.yaml`. `vi-localization-checker` agent pass mới merge.

---

## ⚠️ Risk & Rollback

| Risk | Severity | Mitigation | Rollback |
|---|---|---|---|
| Trust card tăng abandonment ở Step 1.5 | Medium | A/B test với feature flag `TRUST_CARD_ENABLED`; theo dõi trust_acceptance_rate ≥ 90% | Set flag = false |
| Confirm step gây friction, user bỏ giữa chừng | Medium | Confirm chỉ trigger khi thực sự cần (< 10k, > 100 tỷ, ambiguous); default thông minh dựa segment | Disable confirm step qua flag, user nhập trực tiếp |
| Duplicate detection false positive | Low | Bot luôn cho user override với button "Có, asset mới"; không hard-block | Disable detection qua flag |
| Currency disambiguation gây nhầm hơn là giúp | Low | Chỉ trigger khi < 10tr VND VÀ segment không phải starter; có warning log để theo dõi | Disable qua flag |
| Next Best Action CTA spam ngay sau Twin | Low | CTA xuất hiện SAU emoji feedback, là message thứ 4-5 trong flow, có spacing | Move CTA sang Day 2 (gửi qua briefing đầu tiên) |
| Briefing content quality service phụ thuộc LLM, latency tăng | Medium | Cache template-based insights, LLM chỉ dùng khi cần personalize cao; fallback template nếu LLM timeout | Disable personalization, dùng template only |
| Positioning survey bias do user social-desirability | Low | Không hide option "App quản lý chi tiêu" — tăng honest response; ẩn danh trong UI | N/A — survey không phá vỡ flow chính |
| Query-first prompts làm message dài hơn → user skip đọc | Low | Mỗi prompt < 100 chars, đặt cuối message, dùng emoji 💬 tách rõ | Bỏ prompt qua content yaml |
| Migration 4.2.01 backfill placeholder cũ sai | Medium | Backfill heuristic + dry-run mode + operator manual review 5-10 candidate | Backfill script idempotent, có rollback |
| Briefing personalization sai pattern (tự tin sai về user) | High | Template insight có disclaimer ngắn ("Bé Tiền nhận thấy..." thay vì "Bạn nên..."); operator review 5 briefing #1 | Revert sang template generic của Phase 4.1 A.8 |
| Operator vô tình reference số tiền cụ thể trong feedback reply | Medium | Editorial discipline doc (internal); checklist trong operator daily check-in: "tôi có reference số tiền cụ thể không?" | N/A — process rule, không phải code |

---

## ✅ Definition of Done

- [ ] Tất cả 7 story (1.1, 1.2, 2.1, 2.2, 2.3, 3.1, 3.2) acceptance criteria pass.
- [ ] Migration `4.2.01`, `4.2.02`, `4.2.03` applied dev + staging, backfill verified.
- [ ] Test cases `phase-4.2-test-cases.md` pass với 5 persona (re-use từ Phase 4.1); ≥ 95% P0 signed.
- [ ] `vi-localization-checker` agent pass — không hardcoded Vietnamese trong code Phase 4.2.
- [ ] `layer-contract-checker` agent pass.
- [ ] **Trust funnel test:** clean account → onboarding → trust card → accept → first asset (E2E). Đo trust_acceptance_rate ≥ 90% trên staging với 10 fake user.
- [ ] **Confirm step test:** nhập "500" → confirm step 3-option → bấm "500 triệu" → asset save với `is_confirmed=TRUE`, `source_input_raw='500'`.
- [ ] **Duplicate detection test:** thêm 2 cash asset 100tr trong 5 phút → bot prompt duplicate → user override → cả 2 save với warning flag.
- [ ] **Placeholder isolation test:** user dùng demo mode rồi nhập real → query metric "% user log real asset" chỉ count real, không count placeholder.
- [ ] **Next Best Action matrix test:** 9 combination (3 asset state × 3 goal) đều render đúng CTA tương ứng.
- [ ] **Positioning survey test:** user inactive 5 ngày → Day 7 message với survey question → bấm → insert response row.
- [ ] **Briefing #1 quality review:** operator review 5 briefing đầu của founding members → tất cả pass "ít nhất 1 personalized insight" bar.
- [ ] Operator commands từ Phase 4.1 (`/founding_status`, `/cohort_stats`) vẫn hoạt động sau migration 4.2.
- [ ] `kill-criteria.md` updated với positioning misalignment criterion.
- [ ] `content-quality-playbook.md` committed.
- [ ] Editorial discipline guide cho operator (không reference số tiền cụ thể) committed.

---

## 🚧 Out of Scope

Phase 4.2 cố tình **không** làm:

- ❌ **Encryption đầu-cuối** → Phase 5 (sau Phase 4.2). Trust card hiện không mention encryption với user (tránh confuse) — encryption sẽ ship như infrastructure improvement, không cần marketing-style promise upfront.
- ❌ **A/B testing framework** → quá heavy cho cohort 50 user; quan sát trực tiếp đủ tốt cho Phase 4.2 scope.
- ❌ **OCR data quality check** (Claude Vision pipeline) → defer Phase 5.x. Phase 4.2 chỉ guard text input.
- ❌ **Income/cashflow validation** → Phase 4B đã ship cashflow v2, không touch lại. Data quality chỉ apply cho asset input.
- ❌ **Goal-setting flow chi tiết** → Next Best Action chỉ trigger CTA "đặt mục tiêu", không build full goal-setting UX. Goal flow defer sang phase sau.
- ❌ **Multi-language support** → tiếng Việt là primary, EN/VN mixing không scope.
- ❌ **Anonymized analytics export** → operator phải query DB trực tiếp, không có export self-serve.
- ❌ **Survey nhiều câu hơn 1** → 1 câu positioning đủ, không over-survey.
- ❌ **Trust scoring per user** → flag boolean đủ, không cần fine-grained.
- ❌ **Zalo channel activation** → vẫn defer như Phase 4.1 (Phase 5.1-5.3).

---

## 🧭 Recommendations

1. **Story 1.2 (Data Quality) ship trước Story 1.1 (Trust).** Lý do: Data quality là foundation — không có nó, mọi metric của Phase 4.1 (% user log asset thật, intent accuracy) bị inflated. Trust card là UX add — quan trọng nhưng có thể delay vài ngày.

2. **Story 2.2 (Briefing content quality) ưu tiên cao hơn nhìn vào.** Briefing #1 quyết định habit-forming Day 2. Founding member đang trong Phase 4.1 sẽ là cohort đầu test → nếu boring, churn signal sớm.

3. **Operator editorial discipline ngay khi soft launch resume với Phase 4.2.** Vì trust card promise *"chỉ bạn thấy"* — operator (= founder) phải có discipline: không reference cụ thể số tiền user trong feedback reply (vd: thay vì "tôi thấy bạn có 1.5 tỷ", nói "với portfolio của bạn..."). Đây là editorial discipline song song với engineering work, áp dụng cho đến khi encryption ship ở Phase 5.

4. **Operator manual review 5 briefing #1 trong tuần đầu.** Đừng dựa hoàn toàn vào template auto. Trong cohort soft launch 50, 5 manual review là affordable và catches edge cases.

5. **Next Best Action matrix nhỏ trước, expand sau.** 9 CTA strings là starting point — không phải final. Sau Phase 4.2 1 tháng, analyze `next_best_action_taken` distribution → có cell nào CTA chưa work → iterate copy.

6. **Positioning survey không sửa kết quả.** Nếu 35% chọn "App quản lý chi tiêu" sau Day 7 — đừng sửa survey hay biện hộ. Chấp nhận signal, freeze acquisition, redesign positioning. Đây là lý do kill criterion tồn tại.

7. **Phase 4.2 timeline thực tế ~2 tuần — buffer 1 tuần.** Trust + Data Quality work khá lớn vì có nhiều edge case. Đừng commit timeline cứng — flex để fix khi gặp edge case real-world.

8. **Backfill migration cẩn thận.** `4.2.01` có UPDATE để set `is_placeholder_asset=TRUE` cho 50tr demo asset cũ. Heuristic không hoàn hảo — chạy dry-run trước, operator review 5-10 candidate, mới commit. Sai = misclassify user thật là demo → metric sai.

9. **Backfill workflow (option a from PM):** Script chạy dry-run → operator review 5-10 candidate xuất ra CSV → confirm OR mark manual override → commit thật. Idempotent: chạy lại 2 lần không tạo duplicate update.
