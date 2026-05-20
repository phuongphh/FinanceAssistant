# Hướng dẫn dev: xem Admin Dashboard qua cloudflared + Vite hot-reload

Môi trường: **Mac mini M4**, tunnel: **Cloudflare quick tunnel (`cloudflared`)**, flow: **hot-reload (Vite dev server)**.

---

## Tổng quan kiến trúc dev

```
Browser (public URL trycloudflare)
        │
        ▼
cloudflared ──► localhost:5173 (Vite dev server, serve SPA + hot reload)
                       │
                       │  (Vite proxy /api/* → localhost:8000)
                       ▼
                FastAPI :8000 (uvicorn --reload)
                       │
                       ▼
              Postgres :5432, Redis :6379 (docker-compose)
```

Chỉ cần **1 tunnel** trỏ vào port 5173 — Vite tự proxy `/api` về FastAPI nội bộ.

---

## Bước 1 — Khởi động hạ tầng (Postgres + Redis)

```bash
cd ~/FinanceAssistant     # hoặc đường dẫn repo trên Mac mini
docker-compose up -d
docker-compose ps         # xác nhận postgres + redis "healthy"
```

## Bước 2 — Cài deps backend + frontend (một lần)

```bash
# Backend (Python via uv)
uv sync

# Frontend
npm --prefix betien-admin install
```

## Bước 3 — Tạo `.env` (nếu chưa có)

Tối thiểu cần các biến này ở repo root:

```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/finance
REDIS_URL=redis://localhost:6379/0
ADMIN_JWT_SECRET=dev-secret-change-me-32chars-min
INITIAL_ADMIN_EMAIL=admin@local.dev
INITIAL_ADMIN_PASSWORD=ChangeMe!123
```

Các secret khác cho DeepSeek/Claude/Telegram chỉ cần nếu bạn test luồng AI — không bắt buộc để xem dashboard.

## Bước 4 — Migrations + seed admin

```bash
uv run alembic upgrade head
uv run python -m scripts.seed_admin
```

Lệnh seed là idempotent — chạy lại nhiều lần OK.

## Bước 5 — Cho phép Vite nhận host của tunnel

Vite 5+ chặn các Host header lạ. Thêm tạm vào `betien-admin/vite.config.js`:

```js
server: {
  host: true,
  allowedHosts: ['.trycloudflare.com'],   // ← thêm dòng này
  proxy: {
    '/api': { target: 'http://localhost:8000', changeOrigin: true },
  },
  hmr: { clientPort: 443, protocol: 'wss' },  // HMR qua HTTPS tunnel
},
```

Đừng commit thay đổi này lên branch chính nếu chỉ dùng cho dev cá nhân (hoặc gate bằng `process.env.VITE_TUNNEL`).

## Bước 6 — Chạy 3 process song song (mở 3 terminal)

**Terminal 1 — FastAPI:**

```bash
uv run uvicorn backend.main:app --reload --port 8000
```

**Terminal 2 — Vite dev:**

```bash
npm --prefix betien-admin run dev
# in ra: Local: http://localhost:5173/
```

**Terminal 3 — Cloudflare quick tunnel:**

```bash
cloudflared tunnel --url http://localhost:5173
# in ra link kiểu: https://xxxx-xxxx.trycloudflare.com
```

## Bước 7 — Đăng nhập

Mở link `https://xxxx.trycloudflare.com` trên trình duyệt:

- Email: `INITIAL_ADMIN_EMAIL` (mặc định bước 3)
- Password: `INITIAL_ADMIN_PASSWORD`
- Lần đầu login sẽ bị buộc đổi password — đổi xong vào dashboard.
- Scroll xuống dưới **KPI Grid** sẽ thấy section dark header **"Phase 4.3 · Twin USP health — Twin Admin Dashboard"** với 4 sub-section: Engagement Funnel / Loop Health / Comprehension / Delta Distribution.

---

## Troubleshooting nhanh

| Triệu chứng | Nguyên nhân | Fix |
|---|---|---|
| Trang trắng, console báo "Blocked request. This host is not allowed" | Vite chặn host tunnel | Thêm `allowedHosts` (bước 5) |
| Login fail, network tab thấy `/api/admin/auth/login` 404 | Vite không proxy được | Đảm bảo FastAPI :8000 đã chạy trước khi gọi |
| Login 500 "ADMIN_JWT_SECRET not set" | Backend chưa load .env | Restart uvicorn sau khi sửa .env |
| Twin section hiển thị "Không tải được dữ liệu" | Endpoint twin-metrics fail | Check FastAPI logs; nếu bảng metrics rỗng vẫn render được nhưng các số = 0 |
| HMR không reload | WebSocket bị tunnel chặn | OK bỏ qua, refresh tay; hoặc set `hmr.clientPort: 443` (đã thêm bước 5) |

## Mẹo workflow

- Để khỏi mở 3 terminal mỗi lần: viết 1 `Makefile` hoặc dùng `tmux` / `overmind` với Procfile:

  ```
  api: uv run uvicorn backend.main:app --reload --port 8000
  web: npm --prefix betien-admin run dev
  tunnel: cloudflared tunnel --url http://localhost:5173
  ```

- Link `trycloudflare.com` đổi mỗi lần khởi động. Nếu cần URL cố định, đăng ký named tunnel (`cloudflared tunnel create dev-admin`) — nhưng quick tunnel đủ cho thử nhanh.
- An toàn: link tunnel public → bất kỳ ai có URL đều thấy login page. Mặc dù có JWT auth, nên đóng tunnel khi không dùng.
