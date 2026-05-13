# Production Deployment Checklist

Quy trình chuẩn để promote code từ `main` → `prod` và deploy lên VPS.

`prod` là branch deploy-trigger: mọi push lên `prod` sẽ tự động chạy
`.github/workflows/deploy.yml` (SSH vào VPS, `git pull`, `docker compose up -d --build`).
Vì vậy `prod` phải luôn ở trạng thái deployable.

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

Deploy được trigger tự động khi PR merge vào `prod`. Theo dõi:

- [ ] GitHub Actions: `Tự động Deploy lên VPS từ PROD` workflow run xanh
- [ ] SSH vào VPS, check `docker compose ps` — tất cả service `Up (healthy)`
- [ ] Migration tự chạy qua container entrypoint? Nếu **không**:
  ```bash
  ssh vps
  cd ~/FinanceAssistant
  docker compose exec backend alembic upgrade head
  ```
- [ ] `docker compose logs backend --tail 100` — không có ERROR/CRITICAL

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
docker compose exec backend alembic downgrade -1
```

**Lưu ý:** chỉ downgrade migration nếu nó destructive. Phần lớn migration
additive (thêm column/table) có thể để nguyên — code cũ sẽ ignore.

### Rollback container về image cũ

```bash
ssh vps
cd ~/FinanceAssistant
git checkout <previous-prod-commit>
docker compose up -d --build --remove-orphans
```

---

## 9. Tài liệu liên quan

- [`docs/conventions/github-workflow.md`](github-workflow.md) — PR conventions
- [`docs/conventions/coding.md`](coding.md) — coding standards
- [`.github/workflows/deploy.yml`](../../.github/workflows/deploy.yml) — deploy automation
- [`CLAUDE.md`](../../CLAUDE.md) — layer contract & forbidden actions
