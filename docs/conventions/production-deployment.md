# Production Deployment Checklist

Quy trình chuẩn để promote code từ `main` → `prod` và deploy lên VPS.

`prod` là branch deploy-trigger: mọi push lên `prod` sẽ tự động chạy
[`.github/workflows/deploy.yml`](../../.github/workflows/deploy.yml). Workflow này
**không tự deploy** — nó SSH vào VPS rồi gọi
[`scripts/rebuild-finance-prod.sh`](../../scripts/rebuild-finance-prod.sh),
entry point deploy prod **duy nhất**. Script tự lo pull code, backup DB,
build image, chạy migration, smoke test `/health` và rollback nếu fail.
Vì vậy `prod` phải luôn ở trạng thái deployable.

**Kiến trúc prod (đọc trước khi gõ bất kỳ lệnh `docker compose` nào):**

| Thành phần | Giá trị |
|---|---|
| Compose file | `deploy/production/docker-compose.yml` (postgres + redis + **backend** + **scheduler**) |
| Compose project | `financeassistant` |
| Container backend | `finance-backend`, publish `8002:8000` |
| Admin SPA | build **trong** Docker multi-stage image, không build bằng npm trên host |
| TLS / routing | Caddy chạy **ngoài Docker** trên host (`/etc/caddy/Caddyfile`) |

⚠️ `docker-compose.yml` ở **repo root** chỉ có postgres + redis và dùng **cùng**
project name `financeassistant`. Chạy `docker compose up -d --remove-orphans` với
file root sẽ **xoá `finance-backend` và `finance-scheduler`** vì compose coi chúng
là orphan. Mọi lệnh compose trên prod phải chỉ rõ `-f deploy/production/docker-compose.yml`.

⚠️ `scripts/deploy_admin.sh` thuộc kiến trúc **systemctl + caddy cũ** (build SPA bằng
npm trên host, `systemctl restart betien-api`). Đã retired — không gọi trong quy trình này.

---

## 0. Quy ước branch

| Branch | Mục đích | Ai push trực tiếp? |
|---|---|---|
| `main` | Trunk development, mọi feature PR merge vào đây | Không (qua PR) |
| `prod` | Deploy target — push vào đây sẽ trigger deploy lên VPS | Không (chỉ qua PR từ `main`) |
| `claude/main-to-prod-release-*` | Release branch promote main → prod | Auto-generated |

**Không bao giờ** push trực tiếp lên `prod`. Mọi thay đổi phải đi qua PR `main → prod`.

---

## 1. Pre-release — chuẩn bị trên `main`

- [ ] CI trên `main` PASS (test workflow xanh)
- [ ] Migration mới (nếu có) đã được test trên staging/local DB
- [ ] `.env.example` đã cập nhật nếu có key env mới
- [ ] `content/*.yaml` đã được dịch đủ tiếng Việt cho feature mới
- [ ] Phase doc trong `docs/current/` đã được sync với những gì sắp deploy
- [ ] Không còn `TODO`/`FIXME`/`print()` trong code mới
- [ ] Smoke test trên local: golden path + edge case của feature mới

---

## 2. Tạo Release PR (`main` → `prod`)

- [ ] Tạo branch `claude/main-to-prod-release-<suffix>` từ `origin/main`
- [ ] Push branch lên remote
- [ ] Tạo PR với `base = prod`, `head = release branch`
- [ ] Title format: `release: promote main to prod (YYYY-MM-DD)`
- [ ] Body bao gồm các section release notes:
  - **Bug fixes** — liệt kê commit + closes #
  - **Features / enhancements** — liệt kê commit + closes #
  - **Docs / housekeeping**
  - **Database migrations** — file migration cần chạy
  - **Config / env** — env keys mới cần thêm vào prod secrets
  - **Pre-deploy checklist** (section 4 dưới đây)
  - **Rollback plan**

### Xử lý unrelated histories

Nếu `git merge-base origin/prod origin/main` rỗng (lần đầu hoặc prod bị
re-init), dùng merge strategy `ours` để nối history mà giữ main làm
source of truth:

```bash
git checkout claude/main-to-prod-release-<suffix>
git merge -s ours --allow-unrelated-histories origin/prod \
  -m "merge: link prod history into main for prod promotion (YYYY-MM-DD)"
git push -u origin claude/main-to-prod-release-<suffix>
```

Sau merge commit này, các release PR tiếp theo sẽ merge clean bình thường.

---

## 3. Review & merge

- [ ] CI `test` PASS (bắt buộc)
- [ ] CI `review` (code-review bot) — **có thể bỏ qua trên release PR** vì
      diff là delta tích lũy, không phải code mới; các commit substantive đã
      được review riêng khi merge vào main
- [ ] CI `create-pr` (auto-pr.yml) — có thể fail trên release branch vì PR
      đã được tạo thủ công với base=prod; bỏ qua
- [ ] Mergeable state = `clean` hoặc `unstable` (không phải `dirty`)
- [ ] Merge bằng **Merge commit** (không squash) để giữ commit history rõ ràng
- [ ] **Ngay sau khi merge** → deploy workflow sẽ tự chạy. Sang section 4.

---

## 4. Pre-deploy verification (trước khi merge hoặc trong vòng vài phút đầu)

- [ ] Prod secrets manager (GitHub Actions secrets / VPS env file) đã có
      đủ key mới từ `.env.example`
- [ ] DB backup snapshot trong vòng 24h gần nhất (để rollback)
- [ ] Telegram bot token & webhook URL chưa bị thay đổi
- [ ] Redis cache có thể flush nếu cần (nhưng KHÔNG flush tự động)
- [ ] Disk space VPS còn ≥ 20% (Docker build cần room)

---

## 5. Deploy execution

Deploy được trigger tự động khi PR merge vào `prod`. Workflow SSH vào VPS và chạy
`bash scripts/rebuild-finance-prod.sh`; script in log từng bước `[1/7] … [7/7]`.

- [ ] GitHub Actions: `Tự động Deploy lên VPS từ PROD` workflow run xanh
- [ ] Nhận được Telegram notify "deploy thành công" từ script
- [ ] SSH vào VPS, check service state:
  ```bash
  ssh vps
  cd ~/FinanceAssistant
  docker compose -p financeassistant -f deploy/production/docker-compose.yml ps
  ```
  Tất cả service `Up (healthy)`.
- [ ] Migration: script đã chạy `alembic upgrade head` trong container command trước
      khi uvicorn start — **không cần chạy tay**. Nếu backend restart loop, xem log
      để biết migration fail ở đâu.
- [ ] Log sạch, không ERROR/CRITICAL:
  ```bash
  docker compose -p financeassistant -f deploy/production/docker-compose.yml \
    logs backend --tail 100
  ```
- [ ] Health endpoint trả 200: `curl -sS http://localhost:8002/health`

> Nếu workflow đỏ nhưng cần release gấp: SSH vào VPS và chạy tay
> `bash scripts/rebuild-finance-prod.sh` — đây chính là thứ workflow gọi, không có
> bước nào khác. Script từ chối chạy nếu working tree bẩn, không ở branch `prod`,
> hoặc local đang ahead origin.

---

## 6. Post-deploy smoke test (≤ 10 phút sau deploy)

- [ ] Telegram bot phản hồi `/start` bằng welcome message Bé Tiền
- [ ] Gửi 1 transaction test (text) → bot ghi nhận và lưu DB
- [ ] Gửi 1 ảnh receipt → OCR trả kết quả trong < 15s
- [ ] Mở mini-app dashboard → load không lỗi, hiển thị data
- [ ] Scheduler job chạy đúng (check logs lần fire đầu tiên của cron)
- [ ] Notion sync (nếu có) — record mới xuất hiện trong workspace

---

## 7. Monitoring 24h đầu

- [ ] Theo dõi error log mỗi 2h trong 6h đầu, sau đó 1 lần / 6h
- [ ] Theo dõi latency Telegram webhook (P95 < 200ms)
- [ ] Theo dõi LLM API cost (DeepSeek/Claude) — không spike bất thường
- [ ] Theo dõi DB connection pool — không saturated

---

## 8. Rollback plan

Nếu deploy fail hoặc phát hiện regression nghiêm trọng:

### Rollback nhanh (revert merge)

```bash
git checkout prod
git pull origin prod
git revert -m 1 <merge-commit-sha>
git push origin prod
```

Push lên prod sẽ tự trigger deploy lại với code cũ.

### Rollback migration (nếu cần)

```bash
ssh vps
cd ~/FinanceAssistant
docker compose -p financeassistant -f deploy/production/docker-compose.yml \
  exec backend alembic downgrade -1
```

**Lưu ý:** chỉ downgrade migration nếu nó destructive. Phần lớn migration
additive (thêm column/table) có thể để nguyên — code cũ sẽ ignore.

### Rollback container về image cũ

`rebuild-finance-prod.sh` **tự rollback** khi smoke test `/health` fail (trap `ERR`
→ `do_rollback()`), nên bước này chỉ dùng khi deploy "thành công" nhưng phát hiện
regression sau đó.

```bash
ssh vps
cd ~/FinanceAssistant
git reset --hard <previous-prod-commit>
bash scripts/rebuild-finance-prod.sh
```

⚠️ **KHÔNG** dùng `docker compose up -d --build --remove-orphans` với compose file ở
repo root — file đó chỉ có postgres + redis, và vì trùng project name
`financeassistant` nên `--remove-orphans` sẽ xoá `finance-backend` +
`finance-scheduler`, khiến prod mất hẳn backend.

⚠️ Rollback code mà **không** revert migration có thể break app nếu deploy vừa rồi
đổi schema. Backup pre-deploy nằm ở `.backups/pre-deploy-*.sql.gz` trên VPS.

> Có thể chạy qua OpenClaw skill: `ROLLBACK_CONFIRMED=1 bash
> openclaw-skills/finance-devops/scripts/rollback.sh` (script này SSH từ máy admin
> vào prod, cần config SSH sẵn).

---

## 9. Tài liệu liên quan

- [`docs/conventions/github-workflow.md`](github-workflow.md) — PR conventions
- [`docs/conventions/coding.md`](coding.md) — coding standards
- [`.github/workflows/deploy.yml`](../../.github/workflows/deploy.yml) — deploy automation (SSH → gọi script bên dưới)
- [`scripts/rebuild-finance-prod.sh`](../../scripts/rebuild-finance-prod.sh) — entry point deploy prod duy nhất
- [`deploy/production/docker-compose.yml`](../../deploy/production/docker-compose.yml) — compose file thật của prod
- [`openclaw-skills/finance-devops/SKILL.md`](../../openclaw-skills/finance-devops/SKILL.md) — runbook ops (status/logs/rollback)
- [`CLAUDE.md`](../../CLAUDE.md) — layer contract & forbidden actions
