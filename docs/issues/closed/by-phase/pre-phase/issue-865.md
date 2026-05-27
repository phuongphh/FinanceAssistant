# Issue #865

Mini App wealth dashboard không mở được (404 JS + 422 API)

## Mô tả

User bấm menu button "💰 Tài sản" nhưng dashboard không load được, hiển thị spinner "Đang tải tài sản…" rồi báo lỗi.

## Log từ backend

### 1. JS file 404 Not Found

```
INFO:     2405:4802:1bf3:4c50:fd8b:e799:7a38:cab7:0 - "GET /miniapp/static/js/wealth.js?v=bfa7080c92 HTTP/1.1" 404 Not Found
```

### 2. API trả về 422

```
INFO:     2405:4802:1bf3:4c50:fd8b:e799:7a38:cab7:0 - "GET /miniapp/api/wealth/overview?sort=type HTTP/1.1" 422 Unprocessable Content
```

## Môi trường
- Branch: main (608f706)
- Tunnel URL: https://believe-quad-simplified-sodium.trycloudflare.com
- Tài khoản: Bé Tiền Test (telegram user)
