# Issue #703

Bug: ModuleNotFoundError backend.adapters.telegram_service — import path sai

# Issue #689

[Bug] ModuleNotFoundError: `backend.adapters.telegram_service` import sai

## Nguyên nhân

Hai file mới import sai module path:

- `backend/intent/handlers/action_edit_asset.py:33`
- `backend/intent/handlers/nav_expense_dashboard.py:16`

Cả hai đều gọi `from backend.adapters.telegram_service import send_message` nhưng module này không tồn tại.

## Biểu hiện

1. Khi user gửi message, handler được lazy-load → `ModuleNotFoundError`
2. Toàn bộ intent dispatch crash → bot không phản hồi
3. Hệ quả phụ: streamer tạo placeholder rỗng → edit_message_text thất bại với `"there is no text in the message to edit"`
4. Trong log: `route_update failed: update_id=xxx` kèm traceback `No module named 'backend.adapters.telegram_service'`
