# Production Deployment — FinanceAssistant (Docker)

Thư mục này chứa **toàn bộ cấu hình deploy môi trường production** dưới dạng Docker stack. Mọi file ở đây chỉ phục vụ prod — KHÔNG dùng cho dev/test local.

> Dev local vẫn dùng `docker-compose.yml` ở repo root (chỉ chạy `postgres` + `redis`).

---

## 1. Cấu trúc folder

```
deploy/production/
├── README.md              ← file này
├── docker-compose.yml     ← stack đầy đủ: postgres + redis + backend + scheduler
└── deploy.sh              ← script deploy (chạy trên prod server)

# Liên quan ở repo root:
backend/Dockerfile         ← image dùng chung cho backend + scheduler
.dockerignore              ← chặn .env, .venv/, .git/, tests/ leak vào image
.env                       ← (KHÔNG commit) secrets — phải có sẵn trên prod server
```

### Vì sao Dockerfile + .dockerignore không ở trong `deploy/production/`?

- **`.dockerignore`** bắt buộc phải nằm cạnh **build context root**. Build context của ta là **repo root** (vì Dockerfile cần truy cập `backend/`, `alembic/`, `content/`, v.v.).
- **`backend/Dockerfile`** đặt ở folder `backend/` để phản ánh đúng "đây là image của backend service".
- Compose file ở `deploy/production/` reference cả hai qua đường dẫn tương đối:
  ```yaml
  build:
    context: ../..              # = repo root
    dockerfile: backend/Dockerfile
  env_file:
    - ../../.env                # = repo-root/.env
  ```

---

## 2. Pre-requisites trên prod server

| Yêu cầu | Kiểm tra |
|---|---|
| Docker Engine ≥ 24 | `docker --version` |
| Docker Compose plugin v2 | `docker compose version` |
| `curl` | `curl --version` |
| `.env` tồn tại ở repo root | `ls -la /home/evg-user/FinanceAssistant/.env` |
| User chạy script có quyền docker | `docker ps` không cần `sudo` |
| Port 5433 (postgres), 6380 (redis), 8002 (backend) free hoặc dùng đúng container của ta | `ss -lntp \| grep -E '5433\|6380\|8002'` |

---

## 3. First-time migration (từ launchd + compose cũ → full Docker stack)

> Chỉ chạy MỘT lần khi chuyển backend/scheduler từ launchd plist sang Docker.

```bash
# 3.1. SSH vào prod
ssh evg-user@<prod-host>
cd /home/evg-user/FinanceAssistant

# 3.2. Backup data volumes (an toàn — không xóa volume)
docker volume ls | grep finance
# Expect: financeassistant_postgres_data, financeassistant_redis_data
# Nếu tên KHÁC, sửa lại `name:` trong deploy/production/docker-compose.yml volumes section.

# 3.3. Dừng launchd services backend + scheduler
launchctl unload ~/Library/LaunchAgents/com.financeassistant.backend.plist 2>/dev/null || true
launchctl unload ~/Library/LaunchAgents/com.financeassistant.scheduler.plist 2>/dev/null || true

# 3.4. Dừng compose cũ (chỉ pg + redis, container sẽ giữ data volume)
docker compose -f docker-compose.yml down
# KHÔNG dùng `down -v` — `-v` sẽ XÓA volume → mất data.

# 3.5. Pull branch deploy
git fetch origin
git checkout prod          # hoặc branch tương ứng
git pull --ff-only

# 3.6. Chạy deploy script lần đầu
bash deploy/production/deploy.sh
```

Sau bước 3.6, kiểm tra:
- `docker compose -p financeassistant -f deploy/production/docker-compose.yml ps` → 4 services healthy.
- `curl http://localhost:8002/health` → 200 OK.
- Postgres data: `docker exec finance-postgres psql -U finance -d finance_db -c "SELECT count(*) FROM users;"` → khớp số liệu trước migration.

---

## 4. Daily deploy

Mỗi lần release branch `prod` có code mới:

```bash
ssh evg-user@<prod-host>
cd /home/evg-user/FinanceAssistant
bash deploy/production/deploy.sh
```

Script sẽ tự động:

| Bước | Hành động |
|---|---|
| 1 | Check `docker`, `docker compose`, `curl`, `.env` tồn tại |
| 2 | Đảm bảo working tree sạch (refuse nếu dirty) |
| 3 | `git fetch` + check local KHÔNG ahead origin (refuse nếu có commit chưa push) + fast-forward merge |
| 4 | `docker compose build backend scheduler` (cache pip layer nếu requirements không đổi) |
| 5 | `docker compose up -d` → recreate `backend` + `scheduler` (~5-15s downtime), postgres/redis giữ nguyên |
| 6 | Migration `alembic upgrade head` chạy bên trong backend container startup |
| 7 | Health check `http://localhost:8002/health` (timeout 60s, configurable) |
| 8 | Smoke test sâu: `alembic current` từ backend container + `redis-cli ping` (verify runtime deps thật sự reachable, không chỉ static `/health`) |
| 9 | In status + 10 dòng log cuối của backend + scheduler |

### Deploy branch khác `prod` (vd hotfix test)

```bash
DEPLOY_BRANCH=claude/hotfix-xyz bash deploy/production/deploy.sh
```

### Deploy nhanh không cần pull (đã pull thủ công)

```bash
SKIP_PULL=1 bash deploy/production/deploy.sh
```

---

## 5. Rollback

Tình huống: deploy mới fail health check, hoặc phát hiện regression sau khi deploy.

### 5.1. Rollback code + rebuild

```bash
cd /home/evg-user/FinanceAssistant
git log --oneline -10                            # tìm commit ổn định gần nhất
git checkout <good-commit-sha>                   # detached HEAD OK cho rollback nhanh
SKIP_PULL=1 bash deploy/production/deploy.sh
```

### 5.2. Rollback nhanh KHÔNG cần rebuild (nếu container cũ chưa bị xóa cache)

```bash
# Docker không có "previous image" tự động. Cách đảm bảo: tag image trước mỗi deploy.
# Xem §7 Troubleshooting để bật image tagging.
```

### 5.3. Rollback migration

> ⚠️ Migration thường KHÔNG nên rollback ở prod (data loss risk). Nếu thật sự cần:

```bash
docker exec -it finance-backend alembic downgrade -1
# Sau đó deploy lại commit cũ (§5.1).
```

---

## 6. Stop / start / restart từng phần

```bash
# Tất cả lệnh đều dùng prefix dưới đây (lưu ý `--env-file` BẮT BUỘC vì compose mặc định
# tìm `.env` cạnh compose file, không phải repo root):
DC="docker compose --env-file .env -p financeassistant -f deploy/production/docker-compose.yml"

# Dừng tất cả (giữ volume)
$DC down

# Dừng riêng backend (vd để debug)
$DC stop backend

# Restart scheduler sau khi sửa code (lưu ý: cần build lại nếu sửa code)
$DC build scheduler && $DC up -d scheduler

# Xem log realtime
$DC logs -f backend
$DC logs -f scheduler

# Vào shell trong container backend
$DC exec backend bash

# Chạy alembic thủ công
$DC exec backend alembic current
$DC exec backend alembic upgrade head
```

---

## 7. Troubleshooting

### Deploy refuse "Local branch ahead origin"

Local có commit chưa push lên `origin/$BRANCH`. Hai cách xử lý:
- `git push origin $BRANCH` → đẩy commit lên review trước (đường đúng).
- `git reset --hard origin/$BRANCH` → vứt commit local (CHỈ làm nếu chắc chắn).

### Smoke test fail (`alembic current` không chạy được)

Sau khi `/health` pass nhưng `alembic current` từ container fail → backend không kết nối được DB. Nguyên nhân hay gặp:
- `DATABASE_URL` override sai trong `deploy/production/docker-compose.yml` `environment:` block (vd typo `postgres:5432`).
- Postgres container chưa healthy (check `$DC ps`).
- `POSTGRES_PASSWORD` không match giữa pg container và app config.

```bash
$DC exec backend python -c "from backend.config import get_settings; print(get_settings().database_url)"
$DC exec backend alembic current   # xem error message đầy đủ
```

### Health check fail sau deploy

```bash
$DC logs --tail=100 backend         # tìm traceback
$DC ps                              # check container status
$DC exec backend python -c "import backend.main"   # test import
```

Nguyên nhân thường gặp:
- **Migration fail** → container restart loop. Xem log `alembic` ở đầu output.
- **`.env` thiếu key** → check `env_file: ../../.env` resolve đúng, key bắt buộc đầy đủ.
- **Port conflict** → `ss -lntp | grep 8002`. Nếu có process khác (vd launchd cũ) chiếm port, kill nó.

### Volume bị "lost" sau deploy đầu tiên

Triệu chứng: postgres khởi tạo DB rỗng thay vì gắn vào DB cũ.

Nguyên nhân: `name:` trong `volumes:` section KHÔNG match volume cũ.

Fix:
```bash
docker volume ls | grep -i finance       # tìm tên volume cũ
# Sửa `deploy/production/docker-compose.yml` → `volumes.postgres_data.name: <tên cũ>`
$DC down
$DC up -d
```

### Image bị bloat (>2GB)

Kiểm tra `.dockerignore` có ignore `.venv/`, `tests/`, `docs/`, `.git/` chưa:
```bash
docker history finance-backend:latest   # xem layer size
docker run --rm finance-backend du -sh /app/* | sort -h
```

### Cần xem container đang chạy image nào (commit nào)

Hiện tại image không tag commit SHA. Nếu cần, sửa `deploy.sh` để build với tag:

```bash
# Trong deploy.sh, thay `dc build` bằng:
GIT_SHA=$(git rev-parse --short HEAD)
dc build --build-arg GIT_SHA=$GIT_SHA backend scheduler
docker tag finance-backend:latest finance-backend:$GIT_SHA
```

---

## 8. Tham khảo

- Layer contract & quy ước codebase: [`CLAUDE.md`](../../CLAUDE.md)
- GitHub workflow (PR → prod): [`docs/conventions/github-workflow.md`](../../docs/conventions/github-workflow.md)
- Volume backup procedure: chưa có — TODO ở phase sau.
