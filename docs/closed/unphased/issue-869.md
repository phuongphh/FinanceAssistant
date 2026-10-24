# Issue #869

Dashboard API vẫn trả về 401 sau khi fix signature field

## Mô tả

Sau khi deploy fix pop "signature" field (commit 4d75389, issue #867), dashboard API vẫn trả về 401 Unauthorized. Cả wealth dashboard và expense dashboard đều bị.

## Log backend

```
INFO:     2405:4802:1bf3:4c50:fd8b:e799:7a38:cab7:0 - "GET /miniapp/wealth HTTP/1.1" 200 OK
INFO:     2405:4802:1bf3:4c50:fd8b:e799:7a38:cab7:0 - "GET /miniapp/static/js/dashboard_common.js?v=c8d6d09420 HTTP/1.1" 200 OK
INFO:     2405:4802:1bf3:4c50:fd8b:e799:7a38:cab7:0 - "GET /miniapp/static/js/wealth_dashboard.js?v=c8d6d09420 HTTP/1.1" 200 OK
INFO:     2405:4802:1bf3:4c50:fd8b:e799:7a38:cab7:0 - "GET /miniapp/api/version HTTP/1.1" 200 OK
INFO:     2405:4802:1bf3:4c50:fd8b:e799:7a38:cab7:0 - "GET /miniapp/api/wealth/overview?sort=value_desc HTTP/1.1" 401 Unauthorized
INFO:     2405:4802:1bf3:4c50:fd8b:e799:7a38:cab7:0 - "GET /miniapp/api/wealth/overview?sort=value_desc HTTP/1.1" 401 Unauthorized
INFO:     2405:4802:1bf3:4c50:fd8b:e799:7a38:cab7:0 - "GET /miniapp/api/expense-dashboard/overview?source=menu_expenses_report&_t=1779903235397 HTTP/1.1" 401 Unauthorized
```

## Môi trường
- Branch: main (4d75389)
- Tunnel URL: https://dishes-continent-resistance-plc.trycloudflare.com
- Build hash: c8d6d09420
- Tài khoản: Bé Tiền Test (telegram user)
