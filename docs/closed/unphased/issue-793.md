# Issue #793

Webhook returns 500 on non-JSON body — bot responds slowly

# Issue: Webhook trả về 500 khi request body không phải JSON — bot phản hồi chậm

**Nguyên nhân:** `backend/routers/telegram.py:83` gọi `data = await request.json()` không có try/except. Khi request đến webhook với body trống hoặc không phải JSON (ví dụ từ Cloudflare health check / tunnel probe), nó raise `JSONDecodeError` → FastAPI trả 500 → Telegram retry chậm.

**Tác động:**
- Bot phản hồi chậm (Telegram retry sau vài giây)
- `/baocaosang` và các lệnh khác có thể bị delay
- User thấy bot "không phản hồi" hoặc chậm

**Log lỗi:**
```
telegram.py:83 in telegram_webhook
    data = await request.json()
json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
```

**Fix đề xuất:**
1. Thêm try/except cho `await request.json()`, trả về 400 Bad Request nếu body không hợp lệ
2. Hoặc kiểm tra Content-Type header trước khi parse JSON
3. Thêm error handler để 500 không crash toàn bộ webhook

