# Phase 4.2 — Manual Test Cases

<!-- testing-signoff: need to be signed -->
<!--
  Sign-off marker — driven by scripts/archive_phase.py.
  When testing is complete, change "need to be signed" → "signed" on the
  line above. The next archive-phase workflow run will move every
  phase-X-* doc (except the detailed_doc) into docs/archive/.
-->

> **Total estimate:** ~60 test cases across 7 stories + cross-cutting
> **Format:** Mỗi TC có Setup → Steps → Expected → Signoff marker
> **Signoff:** `[unsigned]` mặc định; operator/QA đổi thành `[signed: name-date]` khi pass
> **Persona:** Re-use 5 persona từ Phase 4.1 (P1-P5) để consistency. Quick reference:
>  - **P1** Linh, 32, young_pro (~250tr)
>  - **P2** Anh Tuấn, 41, mass_affluent (~1.8 tỷ)
>  - **P3** Chị Hương, 38, hnw (~6.5 tỷ, low-tech)
>  - **P4** Minh, 28, starter (~60tr)
>  - **P5** Anh Khải, 45, mass_affluent (skeptical, hard-to-wow)

---

## 📋 Test Case Status Summary

| Story | TC Count | Signed | Unsigned |
|---|---|---|---|
| 1.1 Trust Moment | 10 | 0 | 10 |
| 1.2 Data Quality Guardrails | 20 | 0 | 20 |
| 2.1 Next Best Action (9-matrix) | 12 | 0 | 12 |
| 2.2 Briefing Content Quality | 6 | 0 | 6 |
| 2.3 Query-First Prompts | 5 | 0 | 5 |
| 3.1 Day 7 Positioning Survey | 5 | 0 | 5 |
| 3.2 Kill Criterion (docs) | 2 | 0 | 2 |
| Cross-cutting (regression, security, performance, persona, contract) | ~10 | 0 | 10 |
| **Total estimate** | **~70 TCs** | **0** | **70** |

**Batch plan:**
- **Batch 1 (TC001-020):** Story 1.1 Trust (10) + Story 1.2 Data Quality first half (10)
- **Batch 2 (TC021-040):** Story 1.2 Data Quality second half (10) + Story 2.1 Next Best Action (10)
- **Batch 3 (TC041-060):** Story 2.1 rest (2) + Story 2.2 (6) + Story 2.3 (5) + Story 3.1 (5) + Story 3.2 (2)
- **Batch 4 (TC061-070):** Cross-cutting (regression, security, performance, persona, contract)

---

## 🧪 BATCH 1 — Story 1.1 Trust Moment + Story 1.2 Data Quality (first half) (TC001–TC020)

### TC001 — Trust card hiển thị giữa Step 1 và Step 2 (happy path)

**Story:** 1.1 | **Type:** Happy Path | **Priority:** P0 | **Persona:** P1

**Setup:**
- Clean user (chưa onboarding)
- `TRUST_CARD_ENABLED=true`
- Migration `4.2.02` applied

**Steps:**
1. User send `/start`
2. Bấm "🌱 Bắt đầu hành trình"
3. Step 1 hiển thị → bấm "🌱 Hiểu rõ tổng tài sản của tôi"
4. Quan sát message tiếp theo

**Expected:**
- Bot KHÔNG hiển thị Step 2 (asset prompt) ngay
- Trust card hiển thị TRƯỚC Step 2 với:
  - Heading: *"🔒 Bé Tiền tôn trọng tiền bạc của bạn"*
  - 3 bullet về privacy
  - 2 inline button "✅ OK, tiếp tục" / "❓ Tôi có câu hỏi"
- `onboarding_sessions.trust_shown_at = NOW()`
- `onboarding_sessions.trust_accepted_at IS NULL`
- `onboarding_sessions.current_step` chưa advance đến `first_asset`

**Signoff:** [unsigned]

---

### TC002 — Bấm "OK, tiếp tục" → advance Step 2

**Story:** 1.1 | **Type:** Happy Path | **Priority:** P0 | **Persona:** P1

**Setup:** Trust card đang hiển thị (sau TC001)

**Steps:**
1. User bấm "✅ OK, tiếp tục"

**Expected:**
- `onboarding_sessions.trust_accepted_at = NOW()`
- `current_step` advance đến `first_asset`
- Step 2 message hiển thị (prompt nhập tài sản đầu tiên)
- KHÔNG có message intermediate ("đang xử lý" hoặc tương tự)

**Signoff:** [unsigned]

---

### TC003 — Bấm "Tôi có câu hỏi" → prompt nhập câu hỏi

**Story:** 1.1 | **Type:** Happy Path | **Priority:** P0 | **Persona:** P5

**Setup:** Trust card đang hiển thị

**Steps:**
1. User bấm "❓ Tôi có câu hỏi"

**Expected:**
- Bot phản hồi message: *"🌱 Bé Tiền nghe bạn — gõ câu hỏi của bạn ngay đây..."*
- `onboarding_sessions.trust_question_raised_at = NOW()`
- `current_step` vẫn ở trust state (chưa advance)
- Bot ở chế độ "đang chờ user gõ"

**Signoff:** [unsigned]

---

### TC004 — Gõ câu hỏi → tạo feedback record với pre_onboarding_question

**Story:** 1.1 | **Type:** Happy Path | **Priority:** P0 | **Persona:** P5

**Setup:** Sau TC003

**Steps:**
1. User gõ: *"Dữ liệu của tôi có được mã hoá không?"*

**Expected:**
- Tạo row mới trong `feedbacks` với:
  - `user_id` đúng
  - `content = 'Dữ liệu của tôi có được mã hoá không?'`
  - `category = 'pre_onboarding_question'`
  - `priority = 'high'`
  - `status = 'open'`
- Trong `/feedback_inbox` của operator: feedback xuất hiện với flag riêng (vd: 🔔 hoặc tag `[trust_q]`)

**Signoff:** [unsigned]

---

### TC005 — Sau khi gửi câu hỏi → option "Tiếp tục bây giờ" vs "Chờ trả lời"

**Story:** 1.1 | **Type:** Happy Path | **Priority:** P1 | **Persona:** P5

**Setup:** Sau TC004

**Steps:**
1. Bot acknowledge sau khi user gõ câu hỏi
2. Quan sát options tiếp theo

**Expected:**
- Bot acknowledge: *"✓ Bé Tiền đã nhận câu hỏi của bạn. Founder sẽ trả lời sớm nhất có thể."*
- 2 inline button: "▶️ Tiếp tục bây giờ" / "⏸️ Chờ trả lời"
- Nếu user bấm "Chờ trả lời" → bot acknowledge ngắn, không advance state. User có thể `/start` lại sau để resume.

**Signoff:** [unsigned]

---

### TC006 — "Tiếp tục bây giờ" → advance Step 2 với trust_accepted_at

**Story:** 1.1 | **Type:** Happy Path | **Priority:** P0 | **Persona:** P5

**Setup:** Sau TC005

**Steps:**
1. User bấm "▶️ Tiếp tục bây giờ"

**Expected:**
- `trust_accepted_at = NOW()` (vẫn set, vì user đồng ý tiếp)
- Advance đến `first_asset` step
- Step 2 prompt hiển thị
- Câu hỏi user gõ vẫn lưu trong feedbacks → operator vẫn trả lời sau, qua DM/feedback flow

**Signoff:** [unsigned]

---

### TC007 — User đã accept trust trước, /start lại → skip trust card

**Story:** 1.1 | **Type:** Corner Case | **Priority:** P0 | **Persona:** P1

**Setup:**
- User A đã accept trust từ session trước (`trust_accepted_at IS NOT NULL`)
- User /start lại

**Steps:**
1. User send `/start`
2. Bấm "Bắt đầu hành trình"
3. Hoàn tất Step 1 goal question

**Expected:**
- Trust card **KHÔNG** hiển thị lại
- Advance trực tiếp từ Step 1 → Step 2
- `trust_shown_at` không update (giữ nguyên giá trị ban đầu)
- `trust_accepted_at` không update

**Signoff:** [unsigned]

---

### TC008 — Feature flag TRUST_CARD_ENABLED=false → skip trust card

**Story:** 1.1 | **Type:** Rollback Test | **Priority:** P0 | **Persona:** P1

**Setup:**
- Toggle `TRUST_CARD_ENABLED=false`
- Restart bot
- Clean user

**Steps:**
1. Clean user /start → complete Step 1 → expect Step 2

**Expected:**
- Trust card **KHÔNG** hiển thị
- Advance trực tiếp từ Step 1 → Step 2 (giống flow Phase 4.1)
- `trust_shown_at IS NULL`, `trust_accepted_at IS NULL`
- Bot không crash, flow vẫn complete bình thường

**Signoff:** [unsigned]

---

### TC009 — Trust copy có exactly 3 bullets (verify content)

**Story:** 1.1 | **Type:** Contract Check | **Priority:** P0

**Setup:** `trust_card.yaml` đã load

**Steps:**
1. Read content của trust card khi user thấy

**Expected:**
- Heading: *"🔒 Bé Tiền tôn trọng tiền bạc của bạn"*
- **3 bullets** (không phải 4 — encryption commitment đã được bỏ):
  - *"Chỉ bạn thấy chi tiết tài sản — không user nào khác nhìn được"*
  - *"Bạn xoá hoặc sửa bất cứ lúc nào qua /profile"*
  - *"Dự phóng tương lai là tham khảo, không phải lời khuyên đầu tư"*
- KHÔNG có dòng nào mention encryption / "mã hoá đầu-cuối" / "tương lai gần"
- Closing question: *"Sẵn sàng bắt đầu chưa?"*
- 2 buttons với emoji đúng

**Signoff:** [unsigned]

---

### TC010 — Trust acceptance rate metric tracked

**Story:** 1.1 | **Type:** Contract Check | **Priority:** P1

**Setup:**
- 10 user qua trust card
- 9 bấm "OK, tiếp tục", 1 bấm "Tôi có câu hỏi" rồi sau đó "Tiếp tục bây giờ"

**Steps:**
1. Query SQL:
   ```sql
   SELECT
     COUNT(*) FILTER (WHERE trust_shown_at IS NOT NULL) AS shown,
     COUNT(*) FILTER (WHERE trust_accepted_at IS NOT NULL) AS accepted
   FROM onboarding_sessions
   WHERE started_at > NOW() - INTERVAL '1 day';
   ```

**Expected:**
- `shown = 10`
- `accepted = 10` (cả 10 đều đã accept eventually)
- `trust_acceptance_rate = 1.0`
- Target ≥ 0.90 satisfied

**Signoff:** [unsigned]

---

### TC011 — Amount < 10,000 VND → confirm step 3-option

**Story:** 1.2 | **Type:** Happy Path | **Priority:** P0 | **Persona:** P4

**Setup:**
- User ở Step 2, đã accept trust
- `DATA_QUALITY_GUARDRAILS_ENABLED=true`

**Steps:**
1. User gõ: `5000`

**Expected:**
- Bot KHÔNG immediately save asset 5,000đ
- Bot hiển thị confirm: *"🤔 Bạn chắc ý là 5.000đ (năm nghìn)?"*
- 4 button: 5.000đ / 5 triệu / 5 tỷ / Khác
- Asset chưa save (`is_confirmed=FALSE` nếu có pending row, hoặc chưa insert)

**Signoff:** [unsigned]

---

### TC012 — Amount > 100 tỷ → confirm "Số khá lớn"

**Story:** 1.2 | **Type:** Happy Path | **Priority:** P0 | **Persona:** P3

**Setup:** User ở Step 2

**Steps:**
1. User gõ: `150 tỷ`

**Expected:**
- Bot parse được "150 tỷ" → 150,000,000,000 VND
- Bot hiển thị confirm: *"🌱 Số khá lớn — bạn chắc số đúng không?"*
- 2 button: "✅ Đúng, 150 tỷ" / "✏️ Sửa lại"
- Tone không assume bad faith — neutral confirm
- Nếu bấm "Đúng" → save asset với `is_confirmed=TRUE`, `data_quality_warning_type='too_large'`

**Signoff:** [unsigned]

---

### TC013 — Ambiguous format "500" → 3-option disambiguation

**Story:** 1.2 | **Type:** Happy Path | **Priority:** P0 | **Persona:** P1

**Setup:** User ở Step 2

**Steps:**
1. User gõ: `500` (chỉ số, không đơn vị)

**Expected:**
- Bot detect ambiguous → confirm step
- Message: *"🤔 Bé Tiền chưa rõ — bạn ý là:"*
- 4 button hiển thị giá trị cụ thể:
  - 💰 500.000đ (năm trăm nghìn)
  - 💵 500.000.000đ (năm trăm triệu)
  - 🏦 500.000.000.000đ (năm trăm tỷ)
  - ✏️ Khác — nhập lại
- Asset chưa insert vào DB

**Signoff:** [unsigned]

---

### TC014 — Bấm "500 triệu" trong confirm → asset save với is_confirmed=TRUE

**Story:** 1.2 | **Type:** Happy Path | **Priority:** P0 | **Persona:** P1

**Setup:** Sau TC013

**Steps:**
1. User bấm button "💵 500.000.000đ (năm trăm triệu)"

**Expected:**
- Row mới trong `assets`:
  - `amount_vnd = 500000000`
  - `is_placeholder_asset = FALSE`
  - `is_confirmed = TRUE`
  - `source_input_raw = '500'` (string gốc user gõ)
  - `data_quality_warning_type = 'ambiguous_format'` (đã được resolve)
- Bot acknowledge: *"Bé Tiền ghi nhận: 500.000.000đ"*
- Advance đến Twin reveal flow

**Signoff:** [unsigned]

---

### TC015 — Bấm "✏️ Khác" → escape, quay lại prompt

**Story:** 1.2 | **Type:** Happy Path | **Priority:** P1 | **Persona:** P5

**Setup:** Sau TC013, đang ở confirm step

**Steps:**
1. User bấm "✏️ Khác — nhập lại"

**Expected:**
- Bot quay lại prompt Step 2 (nhập tài sản)
- KHÔNG insert asset row
- Pending row (nếu có) với `is_confirmed=FALSE` vẫn giữ trong DB (cho audit) hoặc xoá tuỳ implementation — phải nhất quán
- User có thể gõ lại số khác

**Signoff:** [unsigned]

---

### TC016 — source_input_raw lưu string gốc

**Story:** 1.2 | **Type:** Contract Check | **Priority:** P0

**Setup:** Migration `4.2.01` applied

**Steps:**
1. User gõ "1.5 tỷ" → parse → confirm → save
2. Query `assets` table cho row vừa tạo

**Expected:**
- `amount_vnd = 1500000000`
- `source_input_raw = '1.5 tỷ'` (string nguyên gốc, không normalize)
- Useful cho debugging sau này: nếu parser sai, có thể replay từ raw string

**Signoff:** [unsigned]

---

### TC017 — Default ordering dựa wealth segment

**Story:** 1.2 | **Type:** Happy Path | **Priority:** P1 | **Persona:** P3

**Setup:**
- User P3 (mass_affluent/hnw segment đã infer từ session trước)
- Quay lại thêm asset mới, gõ "500"

**Steps:**
1. User gõ: `500` (ambiguous)
2. Quan sát thứ tự button trong confirm step

**Expected:**
- Button 500 **triệu** hiển thị đầu tiên (likely option cho mass_affluent/hnw)
- Hoặc 500 **tỷ** đầu tiên cho hnw cao (logic implementation chọn)
- 500 **nghìn** xếp cuối (unlikely với mass_affluent)
- Default ordering follow `wealth_segment` hint

**Signoff:** [unsigned]

---

### TC018 — Currency disambiguation: amount < 10tr + segment ≠ starter

**Story:** 1.2 | **Type:** Corner Case | **Priority:** P1 | **Persona:** P2

**Setup:**
- User P2 (mass_affluent segment đã set)

**Steps:**
1. User gõ: `5 triệu` (clear unit, nhưng amount nhỏ với mass_affluent)

**Expected:**
- Bot detect: amount < 10tr VND VÀ segment ≠ starter → currency ambiguity
- Bot prompt: *"🤔 Bé Tiền hỏi nhanh — bạn ý là 5 triệu VND hay 5.000 USD (~120 triệu VND)?"*
- 2 button: 🇻🇳 5 triệu VND / 🇺🇸 5.000 USD
- Nếu bấm VND → save 5,000,000đ
- Nếu bấm USD → save ~120,000,000đ (dùng `USD_VND_RATE` từ ENV)

**Signoff:** [unsigned]

---

### TC019 — Asset class non-amount: "5 căn nhà" → prompt giá trị

**Story:** 1.2 | **Type:** Corner Case | **Priority:** P1 | **Persona:** P3

**Setup:** User ở Step 2

**Steps:**
1. User gõ: `5 căn nhà`

**Expected:**
- Bot detect non-amount (không có số tiền cụ thể) → KHÔNG save raw
- Bot prompt: *"🌱 Bé Tiền cần giá trị ước tính bằng tiền — bạn ước khoảng bao nhiêu?"*
- Có hint trong message: *"(vd: 5 căn nhà tầm 2 tỷ/căn = 10 tỷ — bạn cho Bé Tiền số tổng nhé)"*
- `source_input_raw = '5 căn nhà'` lưu vào pending row hoặc context để debug
- User gõ tiếp số tiền → flow tiếp tục normal validation

**Signoff:** [unsigned]

---

### TC020 — Asset class clarity: save source_input_raw raw string

**Story:** 1.2 | **Type:** Contract Check | **Priority:** P1

**Setup:**
- User trả lời 10 tỷ sau prompt từ TC019

**Steps:**
1. Sau TC019, user gõ "10 tỷ"
2. Query asset row vừa tạo

**Expected:**
- `amount_vnd = 10000000000`
- `source_input_raw = '5 căn nhà'` (giữ context gốc, không phải "10 tỷ")
- Hoặc `source_input_raw = '5 căn nhà → 10 tỷ'` (concatenated, tùy implementation — phải document rõ)
- `is_confirmed = TRUE`
- `asset_type = 'real_estate'` (inferred từ "căn nhà" — bonus nếu có inference)

**Signoff:** [unsigned]

---

## 📊 Batch 1 Summary

20 TCs (TC001-020):

| Type | Count |
|---|---|
| Happy Path | 14 |
| Corner Case | 3 |
| Contract Check | 2 |
| Rollback Test | 1 |

| Priority | Count |
|---|---|
| P0 | 14 |
| P1 | 6 |

**All [unsigned].**

**Story coverage:**
- ✅ Story 1.1 Trust Moment: 10/10 TCs (full coverage)
- 🟡 Story 1.2 Data Quality: 10/20 TCs (first half — validation rules + confirm step + asset class)

**Still needed in Batch 2:**
- Story 1.2 second half: placeholder isolation, duplicate detection, KPI digest extension
- Story 2.1 Next Best Action (9-matrix)

---

*Batch 2 (TC021–040) — Story 1.2 Data Quality second half + Story 2.1 Next Best Action — sẽ append sau khi Batch 1 review.*
