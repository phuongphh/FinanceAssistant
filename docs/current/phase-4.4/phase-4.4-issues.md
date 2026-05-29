# Phase 4.4 — Issues Breakdown

> First-5-Minutes WOW. GitHub-ready issue list. Detail: [`phase-4.4-detailed.md`](phase-4.4-detailed.md).

## 📊 Tổng Quan

| Epic | Tên | Issues | Ưu tiên | Ước lượng |
|---|---|---|---|---|
| E0 | Salutation Foundation | 5 | P0 (chặn tất cả) | ~1 ngày |
| E1 | The Reading | 6 | P0 (WOW chính) | ~2-3 ngày |
| E2 | Screenshot Onboarding | 4 | P2 (rủi ro cao) | ~3-5 ngày |
| E3 | Proactive Companion | 3 | P1 | ~2-3 ngày |

**Tổng:** 4 Epics / 18 issues / ~7-10 ngày. Thứ tự build: E0 → E1 → E3 → E2.

## 🏷️ Label Conventions
- `phase-4.4`, `epic-0`/`epic-1`/`epic-2`/`epic-3`
- `wow-0-salutation` / `wow-1-reading` / `wow-2-screenshot` / `wow-3-proactive`
- `persona-critical` (mọi issue chạm copy Bé Tiền — bắt buộc prompt-tester / vi-localization-checker)

---

## 🅾️ Epic #E0 — Salutation Foundation

### Description
`User` model chưa có trường xưng hô → Reading sẽ gọi nhầm anh/chị. Thêm cột, hỏi
trong onboarding (gộp với bước tên), thread vào mọi surface có giọng nói.

### Success criteria (Epic-level)
- User mới chọn anh/chị/bạn trong onboarding; lưu vào `users.salutation`.
- User cũ (NULL) fallback "bạn" ở mọi surface, không lỗi.
- Reading/Twin/Empathy đều dùng đúng xưng hô.

### Child issues

#### Issue #0.1 — Migration + model cột salutation
- `alembic revision` thêm `users.salutation VARCHAR(10) NULL`.
- `backend/models/user.py`: `salutation: Mapped[str | None] = mapped_column(String(10))` cạnh `display_name`.
- **DoD:** `alembic upgrade head` chạy sạch; user cũ = NULL.

#### Issue #0.2 — set_salutation() + salutation_of() helper
- `onboarding_service.set_salutation(db, user_id, value)` — flush-only.
- Helper `salutation_of(user) -> str` trả "bạn" khi NULL.
- **DoD:** unit test 3 giá trị hợp lệ + fallback NULL→"bạn".

#### Issue #0.3 — Onboarding salutation step
- `handle_name_text_input`: sau `set_display_name` → gửi 3 nút (anh/chị/bạn) thay vì vào thẳng goal.
- Callback handler `_on_salutation_picked` → `set_salutation` → ack → `_send_goal_question`.
- Copy block `salutation` ở `content/onboarding/welcome_v2.yaml`.
- **DoD:** flow integration test name → salutation → goal.

#### Issue #0.4 — Thread salutation vào Empathy + Twin narrative
- `empathy_engine.render_message` + `twin_narrative_service_v2` dùng `salutation_of(user)`.
- **DoD:** test render với cả 3 xưng hô; không còn "anh/chị/bạn" hardcode trong code path đó.

#### Issue #0.5 — /profile sửa xưng hô *(optional T6)*
- Ô đổi xưng hô trong /profile; copy ở `content/profile_copy.yaml`.
- **DoD:** đổi được giá trị, persist; bỏ qua được nếu trượt lịch T6.

---

## 🅰️ Epic #E1 — The Reading ⭐

### Description
WOW phút-1: Bé Tiền "đoán" chân dung tài chính từ goal + tên (zero data), giọng
khiêm tốn nhưng cụ thể, không phán xét. v1 đọc lại trên số thật ở phút 3.

### Success criteria (Epic-level)
- Reading v0 hiện sau goal-pick, trước khi xin số.
- Reading v1 hiện sau khi có số thật, trước Twin teaser.
- 100% đúng xưng hô; 0 câu phán xét; 0 "CFO" user-facing.

### Child issues

#### Issue #1.1 — reading_prompt.py
- `READING_PROMPT` + parse, khuôn `storytelling_prompt.py`. Text cố định ở YAML, cấu trúc prompt ở code.
- **DoD:** prompt build với 3 xưng hô × 3 goal; snapshot test cấu trúc.

#### Issue #1.2 — reading_service.py
- Nhận `{salutation, display_name, goal_label, optional số}` → `call_llm(task_type="reading", user_id=…, shared_cache=False, provider="groq")`. Flush-only.
- **DoD:** service test (mock LLM); xác minh truyền user_id + shared_cache=False.

#### Issue #1.3 — Hook Reading v0 vào _on_goal_picked + flag `READING_ENABLED`
- Sau goal_ack → Reading v0 → `_send_first_asset_prompt`. Placeholder "đang đoán…" khi chờ LLM.
- Feature flag `READING_ENABLED` (mặc định `true`) đọc ở **router/worker** (KHÔNG trong service): tắt → bỏ qua Reading v0/v1, đi thẳng asset prompt.
- **DoD:** integration test flow; test flag on/off (off → không gọi reading_service, onboarding như cũ).

#### Issue #1.4 — Reading v1 trên số thật
- Sau `_save_onboarding_first_asset`, trước `_trigger_first_twin`: đọc lại với số.
- **DoD:** integration test; Twin teaser vẫn chạy ngay sau.

#### Issue #1.5 — Copy block reading (welcome_v2.yaml)
- Câu mở "để em đoán thử…", disclaimer "em đoán", CTA "cho em xem thật".
- **DoD:** `vi-localization-checker` pass.

#### Issue #1.6 — Persona QA gate `persona-critical`
- `prompt-tester` cho 3 xưng hô × ≥3 goal.
- **DoD:** 0 phán xét, 0 "Personal CFO/CFO", xưng hô đúng 100%, đọc thành tiếng không robotic.

---

## 🅱️ Epic #E2 — Screenshot Onboarding

### Description
Chụp màn hình app ngân hàng → OCR → số dư → net worth ~30s. Tái dùng pipeline OCR
hiện có (external OCR + DeepSeek), KHÔNG gọi Claude vision.

### Success criteria (Epic-level)
- Forward screenshot 2-3 bank đầu → ra số dư đúng, có bước confirm.
- Luôn có fallback gõ tay khi parse fail.

### Child issues

#### Issue #2.1 — parse_balance_screenshot()
- `ocr_service.parse_balance_screenshot(image_bytes, mime_type)` — tái dùng external OCR + DeepSeek, prompt trích số dư.
- **DoD:** test với fixture (KHÔNG đọc tests/fixtures hiện có — tạo fixture mới ngoài thư mục cấm); fallback trả None gọn.

#### Issue #2.2 — Bank prompts VCB/Tech/MB
- Prompt nhận diện layout 2-3 bank; fallback message thân thiện.
- **DoD:** parse đúng số dư mẫu mỗi bank.

#### Issue #2.3 — Hook nhánh photo trong onboarding + flag `SCREENSHOT_ONBOARDING_ENABLED`
- ⚠️ **Worker ordering (bắt buộc xử lý):** `backend/workers/telegram_worker.py` hiện route **mọi** photo/image-document tới `photo_receipt.handle_photo_message` (OCR hoá đơn) TRƯỚC khi tới wizard onboarding. Ở bước first-asset, screenshot ngân hàng sẽ bị OCR-hoá-đơn "nuốt" nếu không sửa thứ tự. Giải pháp: kiểm tra onboarding session **trước** nhánh photo_receipt trong worker (hoặc cho `handle_photo_message` delegate sang onboarding khi user đang ở first-asset step). Quyết định cách nào ghi rõ trong PR.
- Update ảnh ở bước first-asset → parse → confirm → `_save_onboarding_first_asset`.
- Feature flag `SCREENSHOT_ONBOARDING_ENABLED` (mặc định `false`, cắt khỏi T6): tắt → nhánh ảnh không parse, chỉ gõ tay; photo_receipt cũ không đổi.
- **DoD:** integration test photo → net worth → Reading v1; test screenshot ở onboarding KHÔNG bị photo_receipt nuốt; test flag off → ảnh không parse số dư.

#### Issue #2.4 — Copy gợi ý screenshot
- `step_2_asset` thêm "hoặc chụp màn hình app ngân hàng gửi em".
- **DoD:** `vi-localization-checker` pass.

---

## 🅲 Epic #E3 — Proactive Companion

### Description
Bé Tiền nhắn trước một cách ấm. Thêm 1 trigger vào empathy_engine đã chạy hourly.

### Success criteria (Epic-level)
- Trigger mới fire qua job hourly, tôn trọng cooldown + daily cap + quiet hours.
- Copy ấm, không phán xét, đúng xưng hô.

### Child issues

#### Issue #3.1 — Trigger im-lặng-sau-onboarding + flag `PROACTIVE_COMPANION_ENABLED`
- `_check_*` mới + đăng ký trong `check_all_triggers`. Điều kiện vd: onboarded nhưng chưa xem Twin lần 2 sau N ngày.
- Feature flag `PROACTIVE_COMPANION_ENABLED` (mặc định `true`) đọc ở **job/worker** (KHÔNG trong service): tắt → `check_all_triggers` bỏ qua trigger mới, trigger empathy cũ vẫn chạy.
- **DoD:** unit test fire/không-fire + cooldown; test flag off → trigger mới không fire, trigger cũ vẫn fire.

#### Issue #3.2 — Copy empathy mới
- `content/empathy_messages.yaml` giọng "em để ý thấy…".
- **DoD:** `vi-localization-checker` + render đúng xưng hô.

#### Issue #3.3 — Verify job hourly (no code change)
- Xác nhận `jobs/check_empathy_triggers.py` pick up trigger mới, không cần sửa.
- **DoD:** test job gọi check_all_triggers bao gồm trigger mới.

---

## 🔗 Dependency Graph

```
E0 (salutation) ──┬──> E1 (Reading, cần xưng hô)
                  ├──> E3 (Empathy render, cần xưng hô)
                  └──> E2 (Reading v1 sau screenshot)
E1 ──> E2 (Reading v1 đọc số từ screenshot)
```

E0 là blocker cứng. E2 có thể cắt khỏi T6 mà không ảnh hưởng E0/E1/E3.
