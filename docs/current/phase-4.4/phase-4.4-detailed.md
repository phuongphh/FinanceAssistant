# Phase 4.4 — First-5-Minutes WOW (The Reading + Salutation + Screenshot + Proactive)

> **Mục tiêu một câu:** Người dùng mới phải có khoảnh khắc WOW ở **giây thứ 30**,
> không phải tuần thứ 2. Twin vẫn là payoff/differentiator — phase này dựng
> *cái hook kéo người ta tới được Twin*.

**Status:** 📋 Planned (chèn trước Phase 5.0 Encryption)
**Duration mục tiêu:** ~7-10 ngày (ship trước soft launch tháng 6/2026)
**Branch:** `claude/determined-fermi-UyOWK`

---

## 🛑 DECISION (29/05/2026) — "The Reading" (WOW #1) đã được GỠ BỎ

Sau khi triển khai và trải nghiệm thực tế, **toàn bộ The Reading (v0 teaser phút-1
+ v1 đọc-lại phút-3) bị cắt khỏi flow first-5-minutes.** Giữ lại **WOW #0
(salutation)** và **WOW #3 (proactive companion)**; onboarding đi thẳng
**goal → asset → Twin** như một mạch liền.

**Vì sao gỡ (3 pain xác nhận):**

1. **Vướng flow (pain #1).** Reading v1 chỉ chạy trên *số thật*
   (`if not demo and is_reading_enabled()`), nên bấm nút **demo** ở bước asset
   âm thầm bỏ qua một nhịp mà disclaimer v0 đã hứa ("cho em xem con số thật") →
   nút demo *làm gãy* WOW.
2. **Chuyển cảnh gập ghềnh (pain #2).** ack → placeholder v1 → đoán → disclaimer
   v1 → "(3/3) Twin" là một chuỗi tự-mâu-thuẫn, hứa-rồi-hứa-lại ngay trước payoff.
3. **Reading v0 quá generic (pain #3).** v0 chạy trên *zero data* (chỉ tên + xưng
   hô + goal) nên về mặt cấu trúc chỉ đẻ ra lời tán kiểu Barnum/cold-read → độc
   với uy tín của một sản phẩm tài chính. Không sửa được bằng prompt tốt hơn.

**Hệ quả kỹ thuật:** xoá `backend/services/reading_service.py`,
`backend/bot/personality/reading_prompt.py`, `tests/test_phase_4_4/test_epic1_reading.py`;
gỡ hook + flag `READING_ENABLED` (`is_reading_enabled`) khỏi `onboarding_v2.py`;
xoá block `reading:` trong `welcome_v2.yaml`, thêm `step_2_asset.asset_ack` bắc cầu
thẳng vào Twin. Test mới: `tests/test_phase_4_4/test_onboarding_no_reading.py`.

> Các phần "The Reading" bên dưới (choreography phút 1/3, Files Touched, Epic 1,
> flag `READING_ENABLED`, DoD) được giữ lại để lưu vết quyết định, nhưng đã
> **không còn hiệu lực** — xem banner này là nguồn sự thật.

---

## 📋 Changelog so với Strategy V3 Roadmap

| Thay đổi | Lý do |
|---|---|
| Thêm Phase 4.4 chèn giữa 4.3 (done) và 5.0 (Encryption) | Soft launch tháng 6 cần một WOW phút-0; Twin là feature lean-forward tuần-2, bị "backloaded" sau bước nhập dữ liệu. |
| Twin **không** bị hạ bệ | Reading = hook (phút 0-1), Twin = payoff (phút 4). Bổ trợ, không thay thế. Xem `strategy.md §The Differentiator`. |
| Phase 5.0 Encryption lùi ~1-1.5 tuần | Chấp nhận được; encryption là infra tháng 7, không chặn soft launch. |

---

## 🎯 Triết Lý Thiết Kế Phase 4.4

### 1. Thiếu 5 phút đầu, không thiếu feature
Chẩn đoán: sản phẩm không thiếu tính năng. Nó thiếu **5 phút đầu tiên**. Twin —
wow-factor đã agreed — chỉ xuất hiện *sau khi* user nhập tài sản (bước ma sát cao
nhất). Người mới rời đi trước khi chạm Twin. Phase 4.4 đưa WOW lên *trước* bước
nhập liệu.

### 2. "Em đoán" — probability over precision, áp dụng cho cả tone
The Reading mở bằng *"Để em đoán thử…"*, không khẳng định chắc nịch. Cùng triết lý
honest-framing của Twin (weather metaphor 🌧️⛅☀️ thay số percentile). Giọng nhất
quán xuyên suốt: khiêm tốn nhưng cụ thể đến mức "ơ sao đúng vậy".

### 3. Xưng hô đúng là tiền đề của mọi tone (WOW #0)
`User` model **chưa có** trường giới tính/xưng hô. Mọi "anh/chị" hiện tại là đoán
mò. The Reading sẽ gọi nhầm ngay giây thứ 30 nếu không có salutation. → WOW #0 là
việc làm **đầu tiên**, chặn mọi WOW phía sau.

### 4. WOW không được phán xét — persona Bé Tiền là ràng buộc cứng
Reading chạm nỗi lo → công nhận điểm mạnh thầm lặng → mời xem số thật. **Không một
chữ** "nên/phải/dạy đời". Đây là chỗ dễ hỏng nhất → bắt buộc chạy qua `prompt-tester`.

### 5. Foundation-before-flash vẫn giữ — chỉ là re-sequence trong cùng phút
Reading v0 (phút 1) chạy trên *zero data* (chỉ goal + tên + xưng hô). Reading v1
(phút 3) chạy trên *số thật*. WOW không thay thế dữ liệu đầy đủ — nó là cây cầu cảm
xúc dẫn người dùng *tự nguyện* cung cấp dữ liệu.

### 6. Tận dụng hạ tầng có sẵn, không xây mới
- Reading dùng `llm_service.call_llm` (đã có), khuôn theo `storytelling_prompt.py`.
- Screenshot **nhân bản** `ocr_service.parse_receipt_image` (external OCR + DeepSeek),
  KHÔNG gọi Claude vision trực tiếp.
- Proactive companion = thêm 1 trigger vào `empathy_engine` đã chạy hourly.

---

## 🎬 Choreography "5 phút đầu" (mục tiêu trải nghiệm)

| Phút | Surface | WOW | Trạng thái |
|---|---|---|---|
| 0 | `_send_welcome_and_goal` | Mở cảm xúc, CHƯA xin số | có sẵn, chỉnh copy |
| 0.5 | `handle_name_text_input` → salutation | 🫱 **WOW #0** — hỏi tên + xưng hô (anh/chị/bạn) | **MỚI** |
| ~~1~~ | ~~`_on_goal_picked` → Reading~~ | ~~🪞 **WOW #1** — "để em đoán thử về anh…"~~ | ❌ **GỠ** (xem banner) |
| 2 | `_send_first_asset_prompt` | 📸 **WOW #2** — chụp screenshot / gõ số | **MỚI** (nhánh photo) |
| ~~3~~ | ~~`reading_service` (v1)~~ | ~~🪞 Reading đọc lại trên số thật~~ | ❌ **GỠ** — thay bằng `step_2_asset.asset_ack` bắc cầu thẳng vào Twin |
| 4 | `_trigger_first_twin` | 💎 "đây là anh hôm nay. Xem anh 2030?" | có sẵn |
| 5 | `mark_twin_shown` + founding | Gieo quan hệ + badge | có sẵn |
| sau | `empathy_engine` | 💬 **WOW #3** — Bé Tiền nhắn trước | **MỚI** (trigger + copy) |

---

## 🗂️ Cấu Trúc Thay Đổi

### Files Touched

| File | WOW | Thay đổi |
|---|---|---|
| `alembic/versions/*_add_salutation.py` | #0 | **MỚI** — cột `salutation VARCHAR(10) NULL` |
| `backend/models/user.py` | #0 | thêm `salutation: Mapped[str \| None]` cạnh `display_name` |
| `backend/services/onboarding_service.py` | #0 | thêm `set_salutation()` (flush-only) |
| `backend/bot/handlers/onboarding_v2.py` | #0,#2 | salutation step + nhánh photo (~~Reading hook~~ ❌ đã gỡ) |
| `content/onboarding/welcome_v2.yaml` | #0,#2 | block `salutation`, `step_2_asset.asset_ack`, gợi ý screenshot (~~block `reading`~~ ❌ đã gỡ) |
| ~~`backend/bot/personality/reading_prompt.py`~~ | ~~#1~~ | ❌ **ĐÃ XOÁ** (xem banner DECISION) |
| ~~`backend/services/reading_service.py`~~ | ~~#1~~ | ❌ **ĐÃ XOÁ** (xem banner DECISION) |
| `backend/services/ocr_service.py` | #2 | thêm `parse_balance_screenshot()` |
| `backend/bot/personality/empathy_engine.py` | #3 | thêm `_check_*` trigger + đăng ký |
| `content/empathy_messages.yaml` | #3 | copy trigger mới (giọng "em để ý thấy…") |
| `backend/services/_salutation.py` (hoặc util) | all | helper `salutation_of(user) -> str` fallback "bạn" |
| `backend/bot/personality/empathy_engine.py::render_message` | all | thread salutation |
| `backend/twin/services/twin_narrative_service_v2.py` | all | thread salutation (nhất quán giọng) |
| `content/profile_copy.yaml` | #0 | ô sửa xưng hô trong /profile (nhẹ, optional cho T6) |

### New Database Tables / Columns
- `users.salutation VARCHAR(10) NULL` — giá trị `"anh" | "chị" | "bạn"`. NULL cho user
  cũ → fallback `"bạn"`. Không bảng mới.

---

## 🏗️ Epics & Stories

### Epic 0 — Salutation Foundation (WOW #0)
**Mục tiêu:** Bé Tiền biết xưng hô đúng trước khi nói câu Reading đầu tiên.

- **0.1** Migration + model: cột `users.salutation` nullable.
- **0.2** `set_salutation()` service (flush-only) + `salutation_of(user)` helper fallback "bạn".
- **0.3** Onboarding step: sau khi tên hợp lệ → 3 nút (anh/chị/bạn) → callback `_on_salutation_picked` → set → vào goal. Copy ở `welcome_v2.yaml`.
- **0.4** Thread salutation vào `empathy_engine.render_message` + `twin_narrative_service_v2` để giọng nhất quán toàn sản phẩm.
- **0.5** /profile: ô đổi xưng hô (xử lý đoán-sai). *Optional cho T6, làm nếu kịp.*

### ~~Epic 1 — The Reading (WOW #1)~~ ❌ GỠ BỎ (29/05/2026)
**Quyết định:** cắt toàn bộ Epic 1. Xem banner **DECISION** đầu doc cho lý do
(3 pain: vướng flow demo, chuyển cảnh gập ghềnh, v0 generic-trên-zero-data hại
uy tín). Onboarding nay đi thẳng goal → asset → Twin; `step_2_asset.asset_ack`
thay cho cả v0 lẫn v1. Stories 1.1–1.6 dưới đây giữ để lưu vết, **không còn thực thi.**

- ~~**1.1** `reading_prompt.py`: `READING_PROMPT` + parse.~~ → file đã xoá.
- ~~**1.2** `reading_service.py`: `call_llm(task_type="reading", …)`.~~ → file đã xoá.
- ~~**1.3** Hook v0 vào `_on_goal_picked`.~~ → hook + flag đã gỡ.
- ~~**1.4** Reading v1 sau `_save_onboarding_first_asset`.~~ → thay bằng `asset_ack`.
- ~~**1.5** block `reading` trong `welcome_v2.yaml`.~~ → block đã xoá.
- ~~**1.6** Persona QA `prompt-tester`.~~ → không còn prompt để QA.

### Epic 2 — Zero-effort Screenshot Onboarding (WOW #2)
**Mục tiêu:** "chụp màn hình app ngân hàng → 30 giây thấy tài sản".

- **2.1** `ocr_service.parse_balance_screenshot()`: tái dùng external OCR + DeepSeek, prompt trích *số dư* (không phải khoản chi).
- **2.2** Bank prompt cho 2-3 bank đầu: VCB / Techcombank / MB. Fallback "em chưa đọc được, anh gõ tay giúp em".
- **2.3** Hook nhánh photo trong `handle_asset_text_input` (hoặc handler ảnh tương ứng) → parse → net worth → cùng đường vào `_save_onboarding_first_asset`.
- **2.4** Copy gợi ý trong `step_2_asset` (welcome_v2.yaml): "hoặc chụp màn hình app ngân hàng gửi em".

> **Rủi ro cao nhất phase này** — OCR phụ thuộc layout từng bank. Bắt đầu hẹp (2-3 bank), luôn có fallback gõ tay. Nếu trượt lịch T6 → cắt sang phase sau, KHÔNG block #0/#1/#3.

### Epic 3 — Proactive Companion (WOW #3)
**Mục tiêu:** Bé Tiền nhắn trước một cách ấm, không phán xét.

- **3.1** Thêm `_check_*` trigger vào `empathy_engine` (vd "im lặng sau onboarding nhưng chưa xem Twin lần 2"), đăng ký trong `check_all_triggers`.
- **3.2** Copy ở `content/empathy_messages.yaml` giọng "em để ý thấy…", render qua `render_message` (đã thread salutation ở 0.4).
- **3.3** KHÔNG đổi `jobs/check_empathy_triggers.py` — job hourly 7h-22h đã gọi `check_all_triggers`.

---

## 📐 Layer Mapping (tuân thủ Layer Contract)

| Việc | Layer đúng |
|---|---|
| Hỏi xưng hô, route Reading, nhánh photo | `bot/handlers/onboarding_v2.py` (handler) |
| Logic Reading, set_salutation, parse screenshot | `services/` (flush-only, KHÔNG commit) |
| Gọi DeepSeek/Groq | qua `llm_service.call_llm` (đã wrap adapter) |
| Gửi tin nhắn | `send_message` / `get_notifier()` (KHÔNG import telegram_service trong service) |
| Mọi chuỗi tiếng Việt | `content/*.yaml` (KHÔNG hardcode trong .py) |
| Commit transaction | worker boundary (KHÔNG trong handler/service) |

---

## ⚠️ Risk & Rollback

| Rủi ro | Mức | Giảm thiểu |
|---|---|---|
| Reading "đoán sai" → mất tin | Cao | Framing "em đoán thử", không khẳng định; v1 đọc lại trên số thật ngay sau. |
| Reading lỡ giọng phán xét | Cao | `prompt-tester` gate bắt buộc trước merge; persona test trong DoD. |
| OCR screenshot sai số dư | Cao | Bắt đầu 2-3 bank, luôn confirm số trước khi lưu, fallback gõ tay. |
| Xưng hô sai (đoán nhầm) | Trung | User tự chọn (không đoán); ô sửa /profile; fallback "bạn" an toàn. |
| LLM latency phá nhịp phút-1 | Trung | `provider="groq"` sub-second; có "đang đoán…" placeholder. |
| Phase 5.0 trượt thêm | Thấp | Encryption là infra tháng 7, không chặn soft launch. |

**Rollback — feature flags (env, đọc ở router/worker, KHÔNG đọc trong service):**

| Flag | Mặc định T6 | Tắt → hành vi |
|---|---|---|
| ~~`READING_ENABLED`~~ | — | ❌ **GỠ BỎ** — Reading đã xoá hẳn, không còn flag. Onboarding luôn đi thẳng goal → asset → Twin. |
| `SCREENSHOT_ONBOARDING_ENABLED` | `false` (cắt khỏi T6 mặc định) | Nhánh ảnh ở first-asset không parse; chỉ nhận gõ tay. |
| `PROACTIVE_COMPANION_ENABLED` | `true` | `check_all_triggers` bỏ qua trigger mới; các trigger empathy cũ vẫn chạy. |

Salutation KHÔNG có flag: cột nullable, không bao giờ tắt — nếu skip step thì
fallback "bạn" (an toàn cho user cũ NULL). Mỗi flag có một issue định nghĩa tên +
nơi đọc + test on/off (xem Issue #1.3, #2.3, #3.1 trong issues doc).

---

## ✅ Definition of Done

- [ ] Migration salutation applied; user cũ fallback "bạn" không lỗi.
- [ ] Onboarding hỏi tên + xưng hô (3 nút) trước goal.
- [x] ~~Reading v0/v1~~ → **GỠ BỎ**; onboarding đi thẳng goal → asset → Twin; `asset_ack` bắc cầu, demo path sạch (test `test_onboarding_no_reading.py`).
- [ ] Screenshot parse số dư ≥ 2 bank với fallback gõ tay (hoặc cắt scope có ghi chú).
- [ ] Empathy trigger mới gửi qua job hourly, copy ấm, đúng xưng hô.
- [ ] `vi-localization-checker` pass; 0 chuỗi VN hardcode; mọi copy ở YAML.
- [ ] `layer-contract-checker` pass; 0 `db.commit()` trong service.
- [ ] Twin teaser phút-4 vẫn nguyên (không regression onboarding v2).
- [ ] 2 feature flag còn lại (`SCREENSHOT_ONBOARDING_ENABLED`, `PROACTIVE_COMPANION_ENABLED`) đọc ở router/worker; mỗi flag có test on/off; tắt được riêng không lỗi. (`READING_ENABLED` đã gỡ.)

---

## 🚧 Out of Scope

- Reading "premium" dài (multi-screen) — phase sau.
- Screenshot cho >3 bank, ví điện tử (Momo/ZaloPay) — phase sau.
- Đổi xưng hô qua natural language ("gọi mình là anh đi") — chỉ qua nút/profile ở 4.4.
- Hạ bệ Twin khỏi vị trí differentiator — KHÔNG làm; Reading bổ trợ.

---

## 🧭 Recommendations / Thứ tự thực thi

1. **Epic 0 trước nhất** (~1 ngày) — chặn mọi thứ phía sau.
2. ~~**Epic 1 The Reading**~~ — ❌ **GỠ BỎ** (xem banner DECISION).
3. **Epic 3 Proactive** (~2-3 ngày) — rẻ, hạ tầng có sẵn.
4. **Epic 2 Screenshot** (~3-5 ngày) — rủi ro cao nhất, làm cuối; cắt được nếu trượt T6.

**Nếu chỉ kịp 1 thứ cho tháng 6:** ship Epic 0 (salutation) + làm flow goal → asset →
Twin thật mượt. WOW thật của sản phẩm là **Twin** ở phút-4; salutation + chuyển cảnh
liền mạch (asset_ack) đưa người dùng tới đó mà không vấp. (The Reading từng được kỳ
vọng là hook phút-30 nhưng thực tế phản tác dụng — xem banner.)
