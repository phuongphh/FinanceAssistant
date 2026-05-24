---
name: finance-devops
description: >
  DevOps cho prod server — trigger deploy, check status, xem logs, rollback
  qua SSH. CHỈ admin được phép dùng (kiểm soát bằng ADMIN_USER_IDS env var).
metadata:
  openclaw:
    requires:
      bins: ["bash", "ssh", "curl"]
---

# Finance DevOps Skill

Skill này cho phép admin trigger thao tác prod (deploy / status / logs / rollback)
trực tiếp từ Telegram, qua SSH vào prod server. Mỗi script là thin wrapper
chạy lệnh trên prod — không chứa business logic.

## Khi nào dùng skill này

- Admin muốn deploy code mới: "deploy prod", "build lại prod", "push lên prod"
- Admin muốn kiểm tra trạng thái: "prod đang chạy gì", "status prod", "version prod"
- Admin muốn xem logs: "logs prod", "tail backend logs", "có lỗi gì không"
- Admin muốn rollback: "rollback prod", "revert deploy", "trở về SHA cũ"

**Không phải admin** → từ chối ngay, KHÔNG chạy bất kỳ command nào.

## Security model

Script tự verify `OPENCLAW_USER_ID` (Telegram user_id do OpenClaw inject) match
1 trong các giá trị trong `ADMIN_USER_IDS` (comma-separated). Nếu không match
→ exit 1 với message "unauthorized" trước khi SSH.

SSH dùng key-based auth (không password). Key chỉ tồn tại trên server chạy
OpenClaw bot, không bao giờ commit vào repo.

### Required env vars (set trên OpenClaw host)

| Var | Ví dụ | Ghi chú |
|---|---|---|
| `ADMIN_USER_IDS` | `123456789,987654321` | Telegram user_id của admin, comma-separated |
| `PROD_SSH_HOST` | `finance.nuitruc.ai` | hostname prod |
| `PROD_SSH_USER` | `evg-user` | user SSH trên prod |
| `PROD_SSH_KEY` | `~/.ssh/finance_prod_ed25519` | path tới private key (default: ssh-agent) |
| `PROD_PROJECT_DIR` | `/home/evg-user/FinanceAssistant` | repo root trên prod |

## Cách thực thi

### Deploy code mới
```bash
bash scripts/deploy.sh
```
SSH vào prod → chạy `scripts/rebuild-finance-prod.sh` → stream output về Telegram.
Script đó tự lo: git pull, DB backup, docker compose down + build + up --wait,
smoke test, admin SPA rebuild, rollback nếu fail.

**Lưu ý**: deploy chỉ chạy từ branch `prod` trên prod server. Nếu code chưa
merge vào `prod`, deploy sẽ refuse.

### Check status
```bash
bash scripts/status.sh
```
Trả về:
- Current SHA (git log -1)
- Container status (`docker compose ps`)
- Last deploy log filename

### Xem logs
```bash
bash scripts/logs.sh [service] [lines]
```
- `service`: `backend` (mặc định) | `scheduler` | `postgres` | `redis`
- `lines`: số dòng tail (mặc định 100)

### Rollback
```bash
bash scripts/rollback.sh
```
SSH vào prod → reset HEAD~1 → rebuild stack. **DB migration không auto-revert**
— nếu schema bị break, cần restore từ `.backups/pre-deploy-*.sql.gz` thủ công.

⚠️ Rollback là destructive — confirm với admin trước khi gọi.

## Output format

### Deploy success
```
✅ Deploy OK — abc1234 (downtime 12s, total 95s)
Mini App: https://finance.nuitruc.ai/miniapp/wealth
Admin:    https://finance.nuitruc.ai/admin/
```

### Deploy fail
```
❌ Deploy FAILED at [compose-up]. Rolled back to xyz9876.
Check /tmp/rebuild-finance-20260524-103000.log on prod.
```

### Status
```
SHA:    abc1234 (3 hours ago) "feat: add foo"
Branch: prod
Services:
  finance-backend    Up 3 hours (healthy)
  finance-scheduler  Up 3 hours
  finance-postgres   Up 5 days (healthy)
  finance-redis      Up 5 days (healthy)
```

## Reference: rebuild-finance-prod.sh phases

| Phase | Description | Failure → |
|---|---|---|
| pre-flight | env keys, dirty tree, branch check | abort, no changes |
| git-pull | fetch + ff-only merge | abort, no changes |
| db-backup | pg_dump qua docker exec → `.backups/` | abort, no changes |
| compose-down | graceful tear down | abort, manual recovery |
| compose-up | build + `up -d --wait` | **rollback** (rebuild old SHA) |
| smoke-test | /health, alembic current, redis ping | **rollback** |
| admin-build | deploy_admin.sh (npm + vite + caddy reload) | abort, services running |
| cleanup | docker image prune, log rotation | warn only |
