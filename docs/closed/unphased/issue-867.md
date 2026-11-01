# Issue #867

Mini App wealth dashboard API trả về 401 Unauthorized

## Mô tả

User bấm menu button "💰 Tài sản" để mở wealth dashboard. Trang HTML + static files tải thành công, nhưng API overview trả về 401.

## Log backend

```
INFO:     2405:4802:1bf3:4c50:fd8b:e799:7a38:cab7:0 - "GET /miniapp/wealth HTTP/1.1" 200 OK
INFO:     2405:4802:1bf3:4c50:fd8b:e799:7a38:cab7:0 - "GET /miniapp/static/css/wealth.css?v=c8d6d09420 HTTP/1.1" 200 OK
INFO:     2405:4802:1bf3:4c50:fd8b:e799:7a38:cab7:0 - "GET /miniapp/static/js/dashboard_common.js?v=c8d6d09420 HTTP/1.1" 200 OK
INFO:     2405:4802:1bf3:4c50:fd8b:e799:7a38:cab7:0 - "GET /miniapp/static/js/wealth_dashboard.js?v=c8d6d09420 HTTP/1.1" 200 OK
INFO:     2405:4802:1bf3:4c50:fd8b:e799:7a38:cab7:0 - "GET /miniapp/static/css/style.css?v=c8d6d09420 HTTP/1.1" 200 OK
INFO:     2405:4802:1bf3:4c50:fd8b:e799:7a38:cab7:0 - "GET /miniapp/api/version HTTP/1.1" 200 OK
INFO:     2405:4802:1bf3:4c50:fd8b:e799:7a38:cab7:0 - "GET /miniapp/api/wealth/overview?sort=value_desc HTTP/1.1" 401 Unauthorized
INFO:     2405:4802:1bf3:4c50:fd8b:e799:7a38:cab7:0 - "GET /miniapp/api/wealth/overview?sort=value_desc HTTP/1.1" 401 Unauthorized
```

## Ghi chú
- Trước đây API trả về 422 (thiếu header X-Telegram-Init-Data) — đã được fix ở commit eee6d53
- Sau fix, API trả về 401 (header có gửi nhưng initData không hợp lệ)

## Môi trường
- Branch: main (eee6d53)
- Tunnel URL: https://dishes-continent-resistance-plc.trycloudflare.com
- Build hash: c8d6d09420
- Tài khoản: Bé Tiền Test (telegram user)
