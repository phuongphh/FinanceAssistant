# Phase 4.2 — Deploy Announcements

> File này chứa toàn bộ communication artifact cho Phase 4.2 (CX Hardening) — phase chèn giữa Phase 4.1 (đang testing) và Phase 5.x.
> Phase 4.2 ship cho cohort founding member đang active từ Phase 4.1 → ROLLING UPDATE, không cần re-onboard user cũ.
> Nội dung gồm: operator deploy checklist, user-facing copy (trust card, confirm step, CTA, survey), internal editorial discipline doc.

---

## 📅 Timeline tổng quan

```
T-2 days  │ Migration `4.2.01`/02/03 dry-run trên staging; backfill placeholder review
T-1 day   │ Operator dogfood toàn bộ Phase 4.2 flow trên test account; manual review briefing #1 cho 5 founding member
T0        │ Deploy production — incremental, không downtime; feature flag bật từng phần
T+1 day   │ Verify metric mới: trust_acceptance_rate, data_quality_warning_count, next_best_action_taken distribution
T+3 days  │ Operator check briefing personalization quality, fix template nếu boring
T+7 days  │ Đếm response Day 7 positioning survey lần đầu; reach 20+ response → check misalignment
T+14 days │ Full Phase 4.2 metric review; quyết định mở rộng cohort 50 → 100 nếu positioning OK
```

**Nguyên tắc rollout:** Phase 4.2 KHÔNG ship "big bang" — feature flag từng story (trust, confirm step, next action) để dễ disable individual nếu có issue.

---

## 🔧 OPERATOR-FACING

### Deploy Checklist (T-1 day)

```markdown
## Bé Tiền Phase 4.2 — Pre-Deploy Checklist

### Migrations
- [ ] `4.2.01_asset_quality_flags` applied dev — verify columns + indexes
- [ ] `4.2.01` backfill script run với `--dry-run` → CSV 5-10 placeholder candidate
- [ ] Operator review CSV: confirm hoặc override mỗi candidate
- [ ] `4.2.01` backfill commit thật với reviewed list
- [ ] `4.2.02_onboarding_trust_state` applied — verify ALTER thành công
- [ ] `4.2.03_positioning_survey` applied — verify UNIQUE constraint

### Feature Flags (default values for soft launch)
- [ ] `TRUST_CARD_ENABLED=true`
- [ ] `DATA_QUALITY_GUARDRAILS_ENABLED=true`
- [ ] `NEXT_BEST_ACTION_ENABLED=true`
- [ ] `BRIEFING_PERSONALIZATION_ENABLED=true`
- [ ] `QUERY_FIRST_PROMPTS_ENABLED=true`
- [ ] `POSITIONING_SURVEY_ENABLED=true`

### Content YAML
- [ ] `trust_card.yaml` validated — đọc full content 1 lần
- [ ] `asset_confirm.yaml` validated — 3-option pattern correct
- [ ] `next_action.yaml` validated — 9 CTA cho 3 asset states × 3 goals
- [ ] `content_quality_templates.yaml` validated — ít nhất 5 template + fallback
- [ ] `positioning_survey.yaml` validated — 4 option labels
- [ ] `vi-localization-checker` agent pass

### Smoke Tests
- [ ] Clean test account → /start → trust card → "OK, tiếp tục" → Step 2 (asset input)
- [ ] Clean test account → /start → trust card → "Tôi có câu hỏi" → gõ câu hỏi → feedback record tạo với `category='pre_onboarding_question'`
- [ ] Nhập "500" → confirm step 3-option → bấm "500 triệu" → asset save với `is_confirmed=TRUE`, `source_input_raw='500'`
- [ ] Nhập "1 tỷ" cách 1 phút → duplicate prompt → user override → cả 2 save
- [ ] Demo mode → đến cuối onboarding → Next Best Action CTA hiện đúng: "Thêm tài sản thật để Twin trở thành của bạn"
- [ ] Real asset + understand_wealth goal → CTA: "Thêm 1 nguồn thu nhập..."
- [ ] First briefing 8h sáng hôm sau → có 1 personalized insight (không generic)
- [ ] Day 7 follow-up → survey 4-option hiển thị → bấm → response insert thành công

### Operator Docs
- [ ] Đọc `operator-editorial-discipline.md` 1 lần — hiểu rule không reference số tiền cụ thể
- [ ] Đọc `content-quality-playbook.md` 1 lần — hiểu briefing review pattern
- [ ] Block 30 phút/ngày 1 tuần đầu cho manual review briefing #1 của 5 founding member

✅ All checked → ready to ship Phase 4.2 to production.
```

### Migration Backfill Workflow (Story 1.2 dependency)

Migration `4.2.01` có UPDATE backfill `is_placeholder_asset=TRUE` cho 50tr demo asset cũ. Workflow:

```bash
# Step 1: Dry-run, export candidate CSV
python scripts/migrations/4_2_01_backfill_placeholder.py --dry-run --output candidates.csv

# CSV columns: asset_id, user_id_snippet, amount_vnd, created_at, onboarding_started_at, heuristic_score
# heuristic_score: confidence rằng đây thật sự là placeholder (0-1)

# Step 2: Operator review CSV manually
# - Bỏ qua hàng nào score > 0.95 (cao confidence)
# - Review hàng score 0.5-0.95 (borderline)
# - Reject hàng score < 0.5 (likely real asset)

# Step 3: Add `decision` column to CSV: "apply" | "skip"
# (Operator có thể dùng spreadsheet để mark)

# Step 4: Run real backfill với reviewed CSV
python scripts/migrations/4_2_01_backfill_placeholder.py --apply --decisions reviewed.csv

# Idempotent: chạy lại không tạo duplicate update
```

**Heuristic for `heuristic_score`:**
- 1.0 = amount = 50,000,000 VND + created_at trong 5 phút sau onboarding_started_at + segment NULL
- 0.7 = amount = 50,000,000 + created_at trong 30 phút sau onboarding_started_at
- 0.4 = amount = 50,000,000 nhưng created_at > 1 giờ sau onboarding
- 0.0 = amount ≠ 50,000,000

Operator review chủ yếu cho 0.4-0.7 range — vùng ambiguous.

---

## 👤 USER-FACING COPY

### Trust Card (Story 1.1) — sau Step 1, trước Step 2

```
🔒 Bé Tiền tôn trọng tiền bạc của bạn

• Chỉ bạn thấy chi tiết tài sản — không user nào khác nhìn được
• Bạn xoá hoặc sửa bất cứ lúc nào qua /profile
• Dự phóng tương lai là tham khảo, không phải lời khuyên đầu tư

Sẵn sàng bắt đầu chưa?

[✅ OK, tiếp tục]  [❓ Tôi có câu hỏi]
```

**Bấm "Tôi có câu hỏi":**

```
🌱 Bé Tiền nghe bạn — gõ câu hỏi của bạn ngay đây.

Founder Bé Tiền sẽ trả lời trong vài giờ tới. Sau khi nhận câu trả lời, bạn có thể tiếp tục onboarding bất cứ lúc nào.
```

**Sau khi user gõ câu hỏi → bot acknowledge:**

```
✓ Bé Tiền đã nhận câu hỏi của bạn. Founder sẽ trả lời sớm nhất có thể.

Bạn muốn tiếp tục onboarding bây giờ, hay chờ câu trả lời rồi mới tiếp?

[▶️ Tiếp tục bây giờ]  [⏸️ Chờ trả lời]
```

### Asset Confirm Step (Story 1.2) — khi amount ambiguous

**User gõ "500":**

```
🤔 Bé Tiền chưa rõ — bạn ý là:

[💰 500.000đ (năm trăm nghìn)]
[💵 500.000.000đ (năm trăm triệu)]
[🏦 500.000.000.000đ (năm trăm tỷ)]
[✏️ Khác — nhập lại]
```

**User gõ amount < 10,000 VND:**

```
🤔 Bạn chắc ý là 5.000đ (năm nghìn)?

[💰 Đúng, 5.000đ]
[💵 Ý mình là 5 triệu]
[🏦 Ý mình là 5 tỷ]
[✏️ Khác]
```

**User gõ amount > 100 tỷ VND:**

```
🌱 Số khá lớn — bạn chắc số đúng không?

[✅ Đúng, 150 tỷ]
[✏️ Sửa lại]
```

**Currency disambiguation (amount < 10tr VND + segment không phải starter):**

```
🤔 Bé Tiền hỏi nhanh — bạn ý là 5 triệu VND hay 5.000 USD (~120 triệu VND)?

[🇻🇳 5 triệu VND]
[🇺🇸 5.000 USD]
```

**Asset class clarity (user gõ non-amount):**

```
🌱 Bé Tiền cần giá trị ước tính bằng tiền — bạn ước khoảng bao nhiêu?

(vd: 5 căn nhà tầm 2 tỷ/căn = 10 tỷ — bạn cho Bé Tiền số tổng nhé)
```

### Duplicate Detection (Story 1.2)

```
🤔 Bạn đã thêm tài sản tương tự cách đây 5 phút (Cash 100 triệu).

Đây có phải là asset mới khác không?

[➕ Có, asset mới]
[🗑️ Không, xoá entry này]
```

### Next Best Action CTA (Story 2.1) — 9 variants

**Format:**

```
💡 Bước tiếp theo dành cho bạn:

[CTA text từ matrix]

[Inline button shortcut]

💬 ...hoặc hỏi Bé Tiền bất cứ điều gì về Twin
```

**9 CTA strings từ `next_action.yaml`:**

| Asset state | understand_wealth | plan_goal | track_spending |
|---|---|---|---|
| **demo** | *Thêm tài sản thật để Twin trở thành của bạn* — [🌱 Thêm tài sản] | *Thêm tài sản thật để Bé Tiền lập kế hoạch chính xác* — [🌱 Thêm tài sản] | *Thêm tài sản thật để xem chi tiêu match được không* — [🌱 Thêm tài sản] |
| **real_no_income** | *Thêm 1 nguồn thu nhập để dự phóng chính xác hơn* — [💵 Thêm thu nhập] | *Thêm thu nhập để Bé Tiền đề xuất mục tiêu khả thi* — [💵 Thêm thu nhập] | *Ghi 1 khoản chi tiêu hôm nay để bắt đầu theo dõi* — [📊 Ghi chi tiêu] |
| **real_with_income** | *Đặt 1 mục tiêu lớn (mua nhà / nghỉ hưu / quỹ dự phòng)* — [🎯 Đặt mục tiêu] | *Tạo mục tiêu đầu tiên — Bé Tiền sẽ track* — [🎯 Đặt mục tiêu] | *Ghi 1 khoản chi tiêu để Bé Tiền học pattern của bạn* — [📊 Ghi chi tiêu] |

### Query-First Soft Prompts (Story 2.3)

**Welcome message** — thêm dòng cuối:

```
💬 Bạn cũng có thể gõ câu hỏi bất cứ lúc nào — Bé Tiền hiểu tiếng Việt
```

**Twin reveal message 3** (sau feedback emoji) — thêm cuối:

```
💬 Có câu hỏi về Twin? Cứ hỏi Bé Tiền nhé
```

**First briefing** — thêm sau button "Bé Tiền đang nói gì?":

```
💬 Hoặc hỏi cụ thể — vd: "sao tài sản của tôi giảm?"
```

**Next Best Action CTA** — đã include trong format ở trên.

### First Briefing Personalized Insight (Story 2.2)

**Examples** (từ `content_quality_templates.yaml`):

**Template 1 — young_pro với 100% cash:**

```
[3 mục briefing standard ở trên]

💡 Bé Tiền nhận thấy: bạn giữ 100% tiền mặt. Người trong segment của bạn thường đầu tư 30-50% — nếu muốn nghe ý kiến, gõ "giải thích đầu tư".
```

**Template 2 — mass_affluent với 1 asset class:**

```
💡 Bé Tiền nhận thấy: portfolio của bạn tập trung vào [stocks/real_estate/crypto]. Diversification có thể giảm rủi ro — muốn nghe phân tích, gõ "diversify".
```

**Template 3 — track_spending goal nhưng chưa có expense log:**

```
💡 Bé Tiền nhận thấy: bạn đã thiết lập theo dõi chi tiêu nhưng chưa ghi khoản nào. Bắt đầu với 1 khoản hôm nay nhé?
```

**Template 4 — hnw với portfolio rõ ràng:**

```
💡 Bé Tiền nhận thấy: với portfolio multi-asset của bạn, biến động hàng ngày có thể không quan trọng bằng allocation review hàng quý. Bé Tiền sẽ nhắc bạn review vào đầu quý sau.
```

**Template 5 — starter mới bắt đầu (encouragement):**

```
💡 Bé Tiền nhận thấy: bạn vừa bắt đầu hành trình tài chính — đây là điều khó nhất. Mỗi ngày Bé Tiền sẽ cho bạn 1 góc nhìn nhỏ để hiểu tài sản của mình hơn.
```

**Fallback (không match template nào):**

```
💡 Bé Tiền nhận thấy: pattern tài sản của bạn đang được Bé Tiền học. Quay lại sau 1 tuần để có insight cụ thể hơn nhé.
```

### Day 7 Positioning Survey (Story 3.1)

**Thêm vào cuối Day 7 follow-up message** (đã có từ Phase 4.1):

```
[Day 7 follow-up message từ Phase 4.1]

---

💭 Bé Tiền tò mò 1 chút — sau 7 ngày dùng thử, bạn thấy Bé Tiền giống nhất với gì?

[📊 App quản lý chi tiêu]
[🤖 Trợ lý tài chính cá nhân]
[🔮 Công cụ nhìn tương lai tài chính]
[🤔 Chưa hiểu rõ]
```

**Acknowledge sau khi user bấm:**

```
✓ Cảm ơn bạn — giúp Bé Tiền hiểu rõ mình hơn 💚
```

---

## 📋 INTERNAL DOCS

### Operator Editorial Discipline (Story D.1)

File: `docs/current/phase-4.2/operator-editorial-discipline.md`

```markdown
# Operator Editorial Discipline

## Rule chính

KHÔNG reference cụ thể số tiền của user trong feedback reply hoặc bất kỳ user-facing message nào.

## Lý do

Trust card promise: *"Chỉ bạn thấy chi tiết tài sản — không user nào khác nhìn được."*

Đây là promise true với user khác — nhưng founder/operator hiện tại có thể query DB và thấy số tiền. Nếu operator reply feedback với nội dung như *"tôi thấy bạn có 1.5 tỷ trong cash..."* → user nhận ra promise sai → trust gãy.

Rule này áp dụng cho đến khi encryption end-to-end ship trong Phase 5.0. Sau encryption ship, operator không thể query plain số tiền nữa → rule này tự nhiên enforce.

## Pattern thay thế

| Tình huống | ❌ KHÔNG nên | ✅ Nên |
|---|---|---|
| User hỏi về portfolio | "Tôi thấy bạn có 1.5 tỷ, chia 60% stocks..." | "Với portfolio của bạn, allocation hiện tại..." |
| User hỏi về budget | "Bạn chi 5 triệu cho ăn uống tháng này" | "Bạn chi nhiều cho ăn uống tháng này — chiếm X% thu nhập" |
| User hỏi Twin | "Twin của bạn dự phóng 2 tỷ trong 5 năm" | "Twin của bạn dự phóng tăng đáng kể trong 5 năm" |
| User hỏi so sánh | "Bạn có 800tr, người segment của bạn thường có 500-1.5tỷ" | "Tài sản của bạn nằm trong segment young_pro/mass_affluent..." |

## Daily check-in checklist (operator)

Mỗi sáng sau khi đọc KPI digest:

- [ ] Hôm qua tôi reply bao nhiêu feedback?
- [ ] Trong các reply đó, tôi có reference số tiền cụ thể của user nào không?
- [ ] Nếu có → đi vào DB sửa message, xin lỗi user nếu cần
- [ ] Note pattern: nếu tôi quên rule này 2 lần/tuần → cần auto-checker

## Exceptions

- Operator có thể reference số tiền **mà user vừa gửi trong cùng message** — vì user đã chia sẻ với operator trực tiếp. Vd: user gõ feedback "tại sao Twin tính sai 500 triệu của em?" → operator có thể trả lời "500 triệu của bạn..."
- Operator có thể reference **% / band / tier** thay vì số tuyệt đối. Vd: "trong top 10% portfolio của Bé Tiền"

## Auto-checker (future)

Phase 4.3+: build agent check feedback_reply text → grep regex số tiền > 6 digit → flag operator review trước khi send.
```

### Content Quality Playbook (Story D.2)

File: `docs/current/phase-4.2/content-quality-playbook.md`

```markdown
# Briefing Content Quality Playbook

## Mục tiêu

Mỗi briefing #1 (và ý lý do tất cả briefing) phải PASS quality bar: chứa ít nhất 1 personalized insight, không phải template generic.

## Editorial rules

Mỗi insight phải có ít nhất 1 trong 3:

1. **So sánh user với segment** (vd: "người trong segment của bạn thường...")
2. **Suggest action cụ thể** (vd: "bắt đầu với 1 khoản hôm nay")
3. **Pose câu hỏi để user follow up** (vd: "muốn nghe ý kiến, gõ...")

## Tone discipline

| Pattern | ✅ Use | ❌ Avoid |
|---|---|---|
| Mở đầu insight | "Bé Tiền nhận thấy..." | "Bạn nên..." (tự tin sai) |
| Suggest action | "...nếu muốn nghe ý kiến, gõ..." | "...bạn phải..." (commanding) |
| Compare | "...thường đầu tư 30-50%..." | "...bạn đang sai vì..." (judgment) |
| Disclaimer | "Đây là quan sát của Bé Tiền, không phải lời khuyên đầu tư." | "Đây là kế hoạch tốt nhất cho bạn." (over-promise) |

## Template library (starter — 5 templates)

[Reference: nội dung trong `content_quality_templates.yaml`]

1. young_pro với 100% cash → insight về diversification
2. mass_affluent với 1 asset class → insight về risk concentration
3. track_spending nhưng chưa log → encouragement to start
4. hnw với multi-asset → quarterly allocation review
5. starter mới bắt đầu → empathy + encouragement

## Manual review process (tuần đầu Phase 4.2)

Operator đọc briefing #1 của 5 founding member đầu trong tuần soft launch resume:

**Per briefing:**
- [ ] Personalized insight hiện diện?
- [ ] Match 1 trong 3 editorial rules (so sánh / suggest action / pose câu hỏi)?
- [ ] Tone match table trên?
- [ ] Không reference số tiền cụ thể (xem editorial discipline doc)?
- [ ] Vietnamese đúng dấu, không lỗi typo?

**Nếu fail bất kỳ check nào:**
1. Note vào playbook (extend pattern library)
2. Fix template/prompt
3. Re-run briefing manually cho user đó
4. Tăng template variety

## Iteration policy

Mỗi tháng:
- Analyze `next_best_action_taken` distribution per template
- Templates nào có action_rate < 30% → flag iterate
- Templates nào có action_rate > 70% → study, replicate pattern
```

---

## 🔄 Migration Deploy Notes

### Migration 4.2.01 — Asset quality flags

**Risk:** Backfill heuristic có thể misclassify real assets là placeholder.

**Mitigation:**
- Dry-run mode → CSV export
- Operator manual review 5-10 candidate trong 0.4-0.7 confidence range
- Idempotent → có thể re-run

**Rollback:**
- ALTER TABLE ... DROP COLUMN ... (data loss, không recoverable)
- Hoặc: chỉ set `is_placeholder_asset=FALSE` cho tất cả → effectively disable flag

### Migration 4.2.02 — Onboarding trust state

**Risk:** Low — chỉ ADD column, không thay đổi data hiện có.

**Rollback:** ALTER TABLE ... DROP COLUMN ... (an toàn).

### Migration 4.2.03 — Positioning survey

**Risk:** Low — CREATE TABLE mới.

**Rollback:** DROP TABLE ... (an toàn).

---

## 🚨 Rollback Plan

Phase 4.2 có **feature flag per story** → có thể disable individual nếu issue:

| Issue type | Rollback action |
|---|---|
| Trust card causing abandonment > 10% | Set `TRUST_CARD_ENABLED=false` → user skip qua trust, vẫn xem confirm step + CTA |
| Confirm step too aggressive | Set `DATA_QUALITY_GUARDRAILS_ENABLED=false` → user nhập trực tiếp, không confirm |
| Next Best Action confusing | Set `NEXT_BEST_ACTION_ENABLED=false` → user skip CTA, đi thẳng "sáng mai 8h..." |
| Briefing personalization wrong pattern | Set `BRIEFING_PERSONALIZATION_ENABLED=false` → fallback template generic |
| Query-first prompts làm message dài | Set `QUERY_FIRST_PROMPTS_ENABLED=false` → bỏ prompts |
| Positioning survey gây churn | Set `POSITIONING_SURVEY_ENABLED=false` → Day 7 message như Phase 4.1 |
| **Migration data corruption** | Backfill rollback script + restore từ pre-deploy DB snapshot |

---

## 📊 Post-Deploy Metrics (T+7 days review)

Operator chạy queries này sau 1 tuần ship Phase 4.2:

```sql
-- 1. Trust funnel
SELECT
  COUNT(*) FILTER (WHERE trust_shown_at IS NOT NULL) AS shown,
  COUNT(*) FILTER (WHERE trust_accepted_at IS NOT NULL) AS accepted,
  COUNT(*) FILTER (WHERE trust_accepted_at IS NOT NULL)::FLOAT / NULLIF(COUNT(*) FILTER (WHERE trust_shown_at IS NOT NULL), 0) AS rate
FROM onboarding_sessions
WHERE started_at > NOW() - INTERVAL '7 days';
-- Target: rate ≥ 0.90

-- 2. Data quality warnings
SELECT data_quality_warning_type, COUNT(*) AS cnt
FROM assets
WHERE data_quality_warning_at > NOW() - INTERVAL '7 days'
GROUP BY data_quality_warning_type;
-- Target: < 10 warnings/day

-- 3. Activation rate (next_best_action_taken)
SELECT
  next_best_action_taken,
  COUNT(*) AS cnt,
  COUNT(*)::FLOAT / SUM(COUNT(*)) OVER () AS pct
FROM onboarding_sessions
WHERE completed_at > NOW() - INTERVAL '7 days'
  AND next_best_action_at IS NOT NULL
GROUP BY next_best_action_taken;
-- Target: > 60% có action != 'none'

-- 4. Positioning survey distribution (cần ít nhất 20 response)
SELECT response, COUNT(*) AS cnt, COUNT(*)::FLOAT / SUM(COUNT(*)) OVER () AS pct
FROM positioning_survey_responses
GROUP BY response;
-- Target: option 2+3 ≥ 60%, option 1+4 ≤ 30%

-- 5. Query-first usage
SELECT
  COUNT(*) FILTER (WHERE entry_mode = 'query') AS query_cnt,
  COUNT(*) FILTER (WHERE entry_mode = 'button') AS button_cnt
FROM intent_logs
WHERE created_at > NOW() - INTERVAL '7 days';
-- Target: query / (query + button) ≥ 30%
```

---

## 📝 Internal Notes

- **Phase 4.2 ship rolling**, không downtime — user đang active từ Phase 4.1 sẽ thấy upgrade từ next interaction.
- **Founding member 50** sẽ là cohort đầu trải nghiệm trust card + confirm step + next action + briefing personalization → quan trọng để feedback nhanh.
- **Operator capacity sẽ tăng tải nhẹ** trong tuần đầu vì cần manual review briefing #1 cho 5 user → block thêm 30 phút/ngày trong calendar.
- **Mọi copy mới phải review qua `vi-localization-checker` agent** trước khi merge.
