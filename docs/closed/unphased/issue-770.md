# Issue #770

Internal dashboard navigation does not reload CSS — WebView uses cached styles

# Issue: Internal navigation giữa các dashboard không load CSS mới (Telegram WebView)

**Nguyên nhân:** Khi chuyển từ Wealth Dashboard → Chi tiêu → Báo cáo (expense dashboard), WebView dùng internal navigation (history.pushState / URL hash), không load lại trang. CSS cũ vẫn được dùng dù file đã thay đổi.

**Luồng hiện tại:**
```
💰 Tài sản (wealth dashboard)
  → bấm "Chi tiêu" (internal nav, không reload)
    → bấm "Báo cáo" (internal nav, không reload)
      → JS load, CSS từ wealth dashboard vẫn còn
```

**Dẫn chứng:**
- CSS file expense.css đã deploy đúng (grid 3 columns, min-height 48px)
- File trên disk có design mới
- Server trả 200 OK (middleware force fresh)
- User đã clear cache + force close app
- Vẫn thấy design cũ

**Yêu cầu:** Chuyển navigation giữa các dashboard sang full page load (dùng location.href thay vì internal navigation), hoặc dùng Telegram WebApp navigation API để force WebView refresh.

