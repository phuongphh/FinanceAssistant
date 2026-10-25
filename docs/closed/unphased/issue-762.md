# Issue #762

Expense Dashboard hangs on loading spinner — API call never reaches backend after deploy

# Issue: Expense Dashboard treo "Đang tải chi tiêu..." sau deploy

**Nguyên nhân:** Khi mở Expense Dashboard trong Telegram Desktop WebView, HTML/CSS/JS load thành công (200 OK) nhưng API call `/miniapp/api/expense-dashboard/overview` không bao giờ đến được backend — request bị mất hoặc timeout.

**Server log (sau restart 01:22, lúc Bệ hạ mở expense 01:31):**
```
GET /miniapp/expense?b=697eaf2770                    → 200 OK
GET /miniapp/static/css/expense.css?v=697eaf2770    → 200 OK
GET /miniapp/static/js/expense_dashboard.js?v=...   → 200 OK
GET /miniapp/api/expense-dashboard/overview?source=... → 🔴 KHÔNG CÓ
```

**Đã có cơ chế live probe** (`_build_bootstrap_script`) nhưng không giúp được trong trường hợp này vì WebView hiển thị spinner loading (JS chạy, gọi fetch API nhưng không nhận response).

**Thông tin thêm:**
- Build hash `697eaf2770` không thay đổi giữa các deploy gần đây
- WebView mở qua menu button `💰 Tài sản` → bấm Chi tiêu → bấm Báo cáo
- Server restart không ảnh hưởng đến WebView đã mở sẵn trong memory
- Request đến các static resource (HTML, CSS, JS) vẫn thành công (200)
- Chỉ request API bị mất — loading mãi không timeout

