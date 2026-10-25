# Issue #912

Tech debt: i18n hóa 6 chuỗi onboarding + gỡ env-read khỏi service layer

## Bối cảnh

Khi triển khai PR gỡ bỏ "The Reading" (#910 / PR #911), hai gate phát hiện 2 khoản tech-debt **có sẵn từ trước** (không phải do diff đó tạo ra). Issue này gom chúng vào một PR riêng, độc lập.

## A. i18n — 6 chuỗi tiếng Việt hardcode trong handler

`vi-localization-checker` báo 6 chuỗi user-facing nằm cứng trong `backend/bot/handlers/onboarding_v2.py` thay vì `content/onboarding/welcome_v2.yaml` (vi phạm quy ước localization).

Chuyển vào YAML với các key:
- `step_name.prompt`, `step_name.invalid`
- `step_2_asset.text_quality_warning` (placeholder `{warning}` + `{amount}`)
- `next_action.session_expired`, `next_action.log_expense_prompt`, `next_action.default_prompt`

## B. Layer contract — service đọc env

`layer-contract-checker` báo `onboarding_service.set_goal()` gọi `is_trust_card_enabled()` (đọc `os.environ`) — service layer **không được đọc env**.

Sửa: `set_goal(db, user_id, goal_code, *, trust_card_enabled: bool)` nhận flag qua tham số; helper `is_trust_card_enabled()` + hằng `TRUST_CARD_FLAG_ENV` chuyển lên handler edge (cùng pattern với `is_v2_enabled` / `is_screenshot_onboarding_enabled`). Bỏ `import os` thừa khỏi service.

## Kiểm thử

- Unit test routing `set_goal` (enabled→trust step, disabled/đã accept→asset step, goal sai→None).
- Test service không còn `is_trust_card_enabled` / `TRUST_CARD_FLAG_ENV`.
- Test flag đọc đúng ở handler edge.
- Test các key copy mới tồn tại + format placeholder sạch.
- Test 6 chuỗi không còn hardcode trong handler.

## Phạm vi

Thuần tech-debt, không đổi hành vi người dùng (chuỗi giữ nguyên văn).

https://claude.ai/code/session_013k3fCnwYSpjuuxEo7oMSUA
