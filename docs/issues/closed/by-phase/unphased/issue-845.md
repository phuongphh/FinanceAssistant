# Issue #845

[bug] Expense mini-app 'Không tải được dữ liệu' — không gọi được API sau khi load


## Nguyên nhân

Route `/miniapp/expense` trả về HTML shell (`expense_dashboard.html`) nhưng JS frontend không gọi được API `/api/expense-dashboard/overview`. So với `/miniapp/wealth` (chạy OK), expense mới thêm trong commit f4a76d7.

## Evidence

Log backend 14:16-14:18:

**Wealth page (chạy OK):**
```
14:16:32 — SELECT users (user_id = UUID ✅ có user)
14:16:32 — SELECT assets (trả về dữ liệu)
14:16:33 — miniapp_loaded (user_id=UUID ✅)
```

**Expense page (lỗi):**
```
14:17:37 — miniapp_opened (user_id=None ❌ không có user)
14:18:07 — miniapp_opened (user_id=None ❌)
14:18:10 — miniapp_opened (user_id=None ❌)
14:18:39 — miniapp_opened (user_id=None ❌)
```

Không có SELECT users / SELECT assets sau khi mở expense page. Frontend không gọi API thành công.

**API test trực tiếp:**
- `/miniapp/api/expense-dashboard/overview` — 422 nếu không có X-Telegram-Init-Data (bình thường)
- `/miniapp/api/wealth/overview` — cũng 422 (tương tự)

## Không phải lỗi DB
- DB SELECT vẫn hoạt động (wealth chạy)
- Error log trống
- Access log không thấy request đến expense API

## Files liên quan
- `backend/miniapp/routes.py` (dòng 685-700 — route /expense không auth, auth ở API layer)
- `backend/miniapp/static/js/expense_dashboard.js` (frontend mới +63 dòng)
- `backend/miniapp/auth.py` — require_miniapp_auth

## Reproduce
1. Bấm nút menu → mở mini app wealth ✅
2. Vào expense dashboard → thấy 'Không tải được dữ liệu' ❌
