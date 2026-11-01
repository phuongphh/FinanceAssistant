# Issue #910

[Phase 4.4] Gỡ bỏ "The Reading" — chữa 3 pain của first-5-minutes WOW

## Bối cảnh

3 pain của flow **first-5-minutes WOW** (Phase 4.4) khi đi cùng Twin onboarding:

1. **Vướng nút demo (pain #1 — flow entanglement).** Reading v1 chỉ chạy trên số **thật** (`if not demo and ...`). Bấm nút *demo* ở bước nhập tài sản → nhảy cóc một nhịp mà v0 disclaimer đã hứa ("cho em xem con số thật") → vỡ wow, không vào được wow#2 (screenshot → Reading v1).
2. **Chuyển cảnh gập ghềnh (pain #2).** ack → v1 placeholder → đoán → v1 disclaimer → "(3/3) Twin" là một chuỗi tự mâu thuẫn, hứa 3 lần trước khi tới payoff.
3. **Reading v0 quá generic (pain #3).** v0 chạy trên **zero financial data** → theo cấu trúc chỉ ra được lời tán dương kiểu Barnum/cold-read → **độc hại với uy tín** của một sản phẩm tài chính. Người dùng nghi ngờ năng lực Bé Tiền — taboo.

## Quyết định (Option A)

**Gỡ bỏ "The Reading" (v0 + v1) hoàn toàn.** Giữ WOW #0 (salutation) + WOW #3 (proactive empathy). Asset ack giờ bắc cầu thẳng vào Twin reveal như **một nhịp liền mạch**: `goal → asset → Twin`.

## Phạm vi thay đổi

- ❌ Xoá `backend/services/reading_service.py`
- ❌ Xoá `backend/bot/personality/reading_prompt.py`
- ❌ Xoá `tests/test_phase_4_4/test_epic1_reading.py`
- ✏️ `backend/bot/handlers/onboarding_v2.py` — gỡ `is_reading_enabled` / `READING_FLAG_ENV` / `_send_reading`; nhánh else của `_save_onboarding_first_asset` gửi `step_2_asset.asset_ack` rồi gọi thẳng `_trigger_first_twin`.
- ✏️ `content/onboarding/welcome_v2.yaml` — gỡ block `reading:`; `step_2_asset.asset_ack` bắc cầu với placeholder `{amount}` + `{name}`.
- ✅ Test mới `tests/test_phase_4_4/test_onboarding_no_reading.py` khoá contract (không cho Reading quay lại).
- 📄 Đồng bộ docs: `phase-4.4-detailed.md`, `phase-4.4-issues.md`, `phase-4.4-test-cases.md`, `phase-status.yaml`, `strategy.md` (Epic E1 → GỠ BỎ, 3 Epics còn hiệu lực).

## Definition of Done

- [x] Reading modules + test bị xoá; không còn import/ref trong source.
- [x] Onboarding đi thẳng `goal → asset → Twin`; nút demo không còn nhảy cóc.
- [x] `asset_ack` dùng placeholder `{amount}`/`{name}`, không hardcode trong code.
- [x] Không còn register "đoán/🔮/bói/tiên tri" trong copy onboarding.
- [x] Toàn bộ test Phase 4.4 xanh (98 passed).
- [x] Gate ruff + vi-localization + layer-contract: thay đổi của PR này sạch.

## Ghi chú (out-of-scope, tech debt có sẵn)

Gate quét được 2 nhóm vi phạm **đã tồn tại từ trước, không nằm trong diff PR này** — đề nghị tách issue follow-up: (a) ~6 chuỗi VN hardcode trong `onboarding_v2.py` (name prompt, invalid-name, quality warning, next-action prompts); (b) `onboarding_service.is_trust_card_enabled()` đọc env trong service layer. Cố tình **không** sửa ở đây để giữ PR gọn quanh việc gỡ Reading.
