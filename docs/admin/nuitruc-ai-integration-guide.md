# Hướng dẫn tích hợp Phase 4.2.5 Admin Observability vào website `nuitruc.ai`

> Mục tiêu: đưa Admin Observability Console đã implemented vào hạ tầng website công ty, dùng domain `nuitruc.ai`.
>
> Khuyến nghị triển khai: **`https://admin.nuitruc.ai`**. Cách này an toàn và ít đụng website chính nhất.
>
> Không khuyến nghị đặt ngay dưới `https://nuitruc.ai/admin` nếu chưa sửa frontend routing, vì admin SPA hiện dùng route gốc `/`, `/login`, `/change-password`.

---

## 1. Bạn đang tích hợp cái gì?

Phase 4.2.5 là **Admin Observability Layer** đã có sẵn trong repo:

- Frontend: React + Vite tại `betien-admin/`.
- Backend: FastAPI admin API tại `/api/admin/*`.
- Static hosting: build frontend vào `backend/static/admin/`.
- Auth: JWT, đổi password lần đầu, rate limit, audit log.
- Database: migration cho admin user, audit log, feature events, license foundation.
- Deploy helper: `scripts/deploy_admin.sh`.
- Caddy template: `infra/caddy/Caddyfile.admin`.

---

## 2. Kiến trúc đề xuất cho `nuitruc.ai`

Dùng subdomain riêng:

```text
Admin browser
  ↓ HTTPS
https://admin.nuitruc.ai
  ↓ Caddy reverse proxy
FastAPI backend :8001
  ├─ /api/admin/*        → Admin API
  └─ /                  → React Admin SPA từ backend/static/admin
```

Lý do nên dùng `admin.nuitruc.ai`:

1. Không ảnh hưởng website chính `https://nuitruc.ai`.
2. Cookie/localStorage/token tách biệt hơn.
3. CORS dễ cấu hình.
4. Route `/login` và `/change-password` chạy đúng ngay, không cần sửa code frontend.

---

## 3. Checklist trước khi deploy

Cần chuẩn bị:

- Server/VPS đang chạy backend FinanceAssistant.
- PostgreSQL đang chạy và `DATABASE_URL` đúng.
- Redis đang chạy, ví dụ `redis://localhost:6379/1`.
- Caddy đã cài.
- DNS tạo bản ghi cho `admin.nuitruc.ai`.
- Node/npm có sẵn để build frontend.
- Python env có thể chạy `alembic` và `python -m scripts.seed_admin`.

---

## 4. Bước 1 — Trỏ DNS

Trong DNS provider của `nuitruc.ai`, tạo record:

```text
Type: A
Name: admin
Value: <IP server production>
TTL: 300
```

Kiểm tra:

```bash
dig +short admin.nuitruc.ai
```

Kết quả phải trả về IP server production.

---

## 5. Bước 2 — Cấu hình biến môi trường backend

Trên server production, thêm các biến môi trường sau:

```bash
export ADMIN_JWT_SECRET="$(openssl rand -hex 32)"
export ADMIN_JWT_EXPIRY_MINUTES=60
export ADMIN_ALLOWED_ORIGIN="https://admin.nuitruc.ai"
export ADMIN_API_RATE_LIMIT_PER_MINUTE=100
export ADMIN_REDIS_URL="redis://localhost:6379/1"
export DATABASE_URL="postgresql+asyncpg://<user>:<password>@<host>:5432/<db>"
```

Seed admin lần đầu:

```bash
export INITIAL_ADMIN_EMAIL="phuongphh@nuitruc.ai"
export INITIAL_ADMIN_PASSWORD="<temporary-strong-password>"
```

Lưu ý:

- Không dùng password mặc định `admin` trên production.
- Sau khi login lần đầu và đổi password, xóa `INITIAL_ADMIN_PASSWORD` khỏi environment.
- `ADMIN_JWT_SECRET` phải giữ ổn định giữa các lần restart. Nếu đổi secret, token cũ sẽ mất hiệu lực.

---

## 6. Bước 3 — Cập nhật Caddy cho `admin.nuitruc.ai`

Tạo hoặc sửa Caddy vhost như sau:

```caddyfile
admin.nuitruc.ai {
    tls phuongphh@nuitruc.ai
    encode zstd gzip

    rate_limit {
        zone admin_api {
            key {remote_ip}
            events 100
            window 1m
        }
    }

    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "strict-origin-when-cross-origin"
        Permissions-Policy "camera=(), microphone=(), geolocation=()"
    }

    handle /api/admin/* {
        reverse_proxy 127.0.0.1:8001
    }

    handle {
        reverse_proxy 127.0.0.1:8001
    }
}
```

Validate trước khi reload:

```bash
caddy validate --config /etc/caddy/Caddyfile
```

Reload:

```bash
caddy reload --config /etc/caddy/Caddyfile
```

---

## 7. Bước 4 — Chạy migration database

Từ root repo:

```bash
alembic upgrade head
```

Việc này tạo/cập nhật các bảng cần cho admin console, gồm:

- `admin_users`
- `admin_audit_log`
- `feature_events`
- `licenses`
- các scope/index liên quan tenant analytics

---

## 8. Bước 5 — Seed admin user

Chạy:

```bash
python -m scripts.seed_admin
```

Kỳ vọng output:

```text
✓ Seeded admin: phuongphh@nuitruc.ai (must change password on first login)
```

Nếu chạy lại lần hai, script phải skip và không tạo duplicate admin.

---

## 9. Bước 6 — Build frontend cho domain mới

Admin frontend đọc API base từ `VITE_API_BASE` lúc build.

Chạy:

```bash
npm --prefix betien-admin install
VITE_API_BASE="https://admin.nuitruc.ai/api/admin" npm --prefix betien-admin run build
```

Sau build, output nằm ở:

```text
betien-admin/dist/
```

---

## 10. Bước 7 — Copy frontend build vào backend static

Chạy:

```bash
mkdir -p backend/static/admin
rm -rf backend/static/admin/*
cp -R betien-admin/dist/. backend/static/admin/
```

FastAPI đã mount thư mục này làm admin SPA nếu `backend/static/admin` tồn tại.

---

## 11. Bước 8 — Restart backend

Nếu service tên là `betien-api`:

```bash
systemctl restart betien-api
```

Kiểm tra health:

```bash
curl -fsS https://admin.nuitruc.ai/health
```

Kỳ vọng response có status healthy.

---

## 12. Bước 9 — Smoke test trên browser

Mở:

```text
https://admin.nuitruc.ai
```

Kiểm tra từng bước:

1. Trang login hiển thị.
2. Login bằng admin đã seed.
3. Hệ thống bắt đổi password lần đầu.
4. Đổi password thành công.
5. Dashboard mở được.
6. KPI cards hiển thị dữ liệu thật.
7. Charts render không lỗi console.
8. User table search/filter/sort/pagination hoạt động.
9. User detail mặc định mask PII.
10. Logout xong vào lại URL protected thì bị redirect về login.

---

## 13. Bước 10 — Xóa secret seed tạm thời

Sau khi login và đổi password thành công:

```bash
unset INITIAL_ADMIN_PASSWORD
```

Nếu bạn lưu biến này trong `.env`, systemd env file, hoặc secret manager, hãy xóa khỏi đó rồi restart service.

---

## 14. Có thể dùng script deploy sẵn không?

Có. Script hiện có là:

```bash
./scripts/deploy_admin.sh
```

Nhưng mặc định script build với `https://admin.betien.vn/api/admin` nếu bạn không override.

Với `nuitruc.ai`, chạy như sau:

```bash
VITE_API_BASE="https://admin.nuitruc.ai/api/admin" \
ADMIN_STATIC_DIR="$(pwd)/backend/static/admin" \
API_SERVICE="betien-api" \
CADDY_CONFIG="/etc/caddy/Caddyfile" \
./scripts/deploy_admin.sh
```

Script sẽ tự:

1. Chạy `alembic upgrade head`.
2. Seed admin idempotent.
3. Install npm dependencies.
4. Build frontend.
5. Copy `dist/` vào `backend/static/admin/`.
6. Restart FastAPI service.
7. Reload Caddy.

---

## 15. Nếu bắt buộc dùng `https://nuitruc.ai/admin`

Không khuyến nghị cho bản hiện tại.

Nếu vẫn muốn dùng path `/admin`, cần thêm việc trước khi deploy:

1. Sửa frontend router để dùng basename `/admin`.
2. Sửa Vite `base` thành `/admin/`.
3. Đổi redirect 401 để về `/admin/login`.
4. Cấu hình Caddy để proxy `/admin/*` và `/api/admin/*` về backend.
5. Đảm bảo website chính `nuitruc.ai` không chiếm route `/admin`.

Ví dụ Caddy path-based:

```caddyfile
nuitruc.ai {
    handle /api/admin/* {
        reverse_proxy 127.0.0.1:8001
    }

    handle /admin* {
        reverse_proxy 127.0.0.1:8001
    }

    handle {
        reverse_proxy 127.0.0.1:<main-website-port>
    }
}
```

Chỉ dùng cách này nếu bạn có thời gian test frontend routing kỹ.

---

## 16. Các endpoint cần kiểm tra nhanh

Sau deploy, chạy:

```bash
curl -fsS https://admin.nuitruc.ai/health
```

Sau khi có token admin, kiểm tra:

```bash
curl -fsS \
  -H "Authorization: Bearer <TOKEN>" \
  https://admin.nuitruc.ai/api/admin/auth/me
```

```bash
curl -fsS \
  -H "Authorization: Bearer <TOKEN>" \
  "https://admin.nuitruc.ai/api/admin/stats/overview?period=30d"
```

---

## 17. Rollback đơn giản

Nếu deploy lỗi:

```bash
journalctl -u betien-api -n 200 --no-pager
```

Rollback code:

```bash
git revert HEAD
```

Nếu cần rollback migration gần nhất:

```bash
alembic downgrade -1
```

Deploy lại bản tốt gần nhất:

```bash
VITE_API_BASE="https://admin.nuitruc.ai/api/admin" ./scripts/deploy_admin.sh
```

---

## 18. Kết luận

Cách nhanh và an toàn nhất:

1. Tạo DNS `admin.nuitruc.ai`.
2. Set env `ADMIN_ALLOWED_ORIGIN=https://admin.nuitruc.ai`.
3. Sửa Caddy vhost sang `admin.nuitruc.ai`.
4. Chạy migration + seed admin.
5. Build frontend với `VITE_API_BASE=https://admin.nuitruc.ai/api/admin`.
6. Copy build vào `backend/static/admin/`.
7. Restart backend + reload Caddy.
8. Smoke test login, đổi password, dashboard, PII masking, logout.
