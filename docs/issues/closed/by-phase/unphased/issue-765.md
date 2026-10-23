# Issue #765

Telegram WebView cache ignores query-string parameters — JS served stale after deploy

# Issue: Telegram WebView cache bypasses query-string cache busters — JS served stale after deploy

**Nguyên nhân:** Telegram WebView sử dụng base URL (không query string) làm cache key. Cache buster `?v=<hash>` không hiệu quả — WebView vẫn trả về 304 dù query string đã thay đổi.

**Bằng chứng từ log backend:**
```
GET /miniapp/expense?b=5de80eebc4&source=menu_expenses_report HTTP/1.1" 200 OK
GET /miniapp/static/js/expense_dashboard.js?v=5de80eebc4 HTTP/1.1" 304 Not Modified
```

**Tác động:** JS cached cũ chạy → API call `/expense-dashboard/overview` không được gọi → loading spinner treo mãi.

**Static files khác (CSS, wealth.js)** cũng bị 304 tương tự.

**Ghi chú:**
- Server trả 304 dựa trên ETag/If-Modified-Since. ETag được tính từ `str(mtime) + "-" + str(size)` → MD5.
- Tele.gram's WebView trên cả Desktop và Mobile đều bị ảnh hưởng.
- HTML (`?b=hash`) không bị vì Telegram dùng URL khác hẳn (không cache).

