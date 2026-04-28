# Scaling Refactor — Phase C (True SaaS scaling)

> **Mục tiêu:** Chạy mượt 10K users. Phase A (stop-the-bleeding) và Phase B
> (cleanup layers) đã merge xong (xem `docs/archive/scaling-refactor-A.md`
> và `docs/archive/scaling-refactor-B.md`).
> **Thời gian:** 1-2 tuần. **Blocks:** Phase 2 SaaS launch (~10K users).
> **Tiền đề:** Notifier port (B3), `shared_cache` (B4), worker pool (A3) đã có.

---

## Bối cảnh

Giai đoạn này giải quyết 6 fix đã defer khi đóng Phase B vì cần infra mới
(Redis, observability) hoặc vì traffic hiện tại (<1K users) chưa cần. Chỉ
implement khi:

- Active user > 1K, **hoặc**
- Webhook latency p95 > 300ms, **hoặc**
- LLM cost > $200/tháng (lúc đó batch + DLQ trả lại tiền nhanh).

Trước ngưỡng đó, code path hiện tại đủ — không over-engineer.

---

## C1 — Morning report gửi song song

### Hiện trạng
`backend/jobs/morning_report_job.py` và `morning_briefing_job.py` lặp tuần
tự `for user in users: await send(...)`. 1K users × 2s = 33 phút → tin
7:00 đến 7:33 → habit forming hỏng.

### Fix
- `asyncio.gather` với semaphore để bound concurrency (vd. 20 song song).
- Rate limit Telegram: bot API ~30 msg/giây; semaphore 20 + jitter là an toàn.
- Per-user failure isolation: `return_exceptions=True`, log từng lỗi.

### Tiền đề
- B3 Notifier port phải xong (hiện đã DONE) — fake notifier để test perf.
- C6 rate limiter per-user nên xong trước, hoặc song song.

### Acceptance
- 1K users hoàn thành trong < 90s (lý tưởng < 60s).
- Một user lỗi không block users khác.

---

## C2 — Batch LLM cho Gmail poll *(điều kiện)*

### Lưu ý quan trọng
CLAUDE.md V2 đã **deprecate Gmail integration** (thay bằng AI
Storytelling). `backend/jobs/gmail_poller.py` còn tồn tại nhưng không
trong roadmap V2. **Re-evaluate trước khi implement** — có thể skip C2
hoàn toàn nếu Gmail đã remove ở Phase 3A/3B cleanup.

### Fix (nếu Gmail vẫn dùng)
- Gộp 50 emails/call thay vì 1 email/call → giảm 98% LLM call cho task.
- Pattern: collect batch → format prompt với markers → parse multi-result.

### Áp dụng pattern cho task khác (relevant V2)
- Batch categorize: gom transaction chưa categorize trong N phút, gửi 1 call.
- Batch storytelling LLM: nếu user gửi nhiều story trong 1 cửa sổ — ít khả năng.

---

## C3 — Redis + ARQ / Celery

### Khi nào cần
- Multi-process worker (uvicorn > 1 instance hoặc Celery worker riêng).
- Background task chạy > 30s (asyncio task in-process bị mất khi reload).
- Cần priority queue (briefing job ưu tiên hơn cleanup job).

### Lựa chọn
- **ARQ** — async-first, Pydantic, ít boilerplate. Recommended cho stack này.
- **Celery** — chuẩn industry, nhiều integration, học cong dốc.

### Migration path
`telegram_updates` table (Phase A) đóng vai trò task table → swap dispatch
từ `asyncio.create_task` sang ARQ enqueue. Webhook logic không đổi.

### Tiền đề
- Redis container đã có sẵn trong `docker-compose.yml`.
- Phase 1 VPS deploy.

---

## C4 — DLQ với exponential backoff

### Hiện trạng
`telegram_updates.status='failed'` là dead letter "thủ công". Không retry,
không alert.

### Fix
- Add `retry_count`, `next_retry_at` columns vào `telegram_updates`.
- Background loop pick up `status='failed' AND next_retry_at < NOW()`.
- Backoff: 1m → 5m → 30m → 2h → give up (alert).
- Cap retry = 4. Sau đó move sang `status='dead'`, gửi alert (Sentry/email).

### Tiền đề
- Cần Sentry hoặc tương đương cho alert (C5).

---

## C5 — Observability (OpenTelemetry)

### Mục tiêu
Trả lời được các câu sau trong < 1 phút:
- Webhook latency p50/p95/p99 hiện tại?
- LLM cost theo user / theo task_type tháng này?
- Job nào failure rate cao nhất tuần qua?
- User X gửi message lúc Y, đường đi của update_id đó qua các handler?

### Stack đề xuất
- **OpenTelemetry SDK** — auto-instrument FastAPI + SQLAlchemy + httpx.
- **Grafana Cloud** free tier hoặc **Honeycomb** free tier — đủ < 10K users.
- Metrics quan trọng: webhook latency, LLM call duration / cost,
  background task duration, queue depth, DB pool checkout time.

### Acceptance
- Dashboard 1 trang hiển thị 5 metrics trên realtime.
- Trace 1 update_id từ webhook → worker → handler → service → response.

---

## C6 — Rate limiter per-user

### Hiện trạng
Không có. User abuse có thể spam webhook → exhaust LLM budget.

### Fix
Token bucket per `user_id`:
- 10 message / phút cho normal user.
- 100 / phút cho voice (vì Whisper nhanh).
- Override admin để raise limit.

### Implementation
- Phase 1 in-memory (single process): `cachetools.TTLCache` với token count.
- Phase 2 Redis (multi-process): `INCR` + TTL pattern.

### Tiền đề
- C3 Redis nếu multi-process. Phase 1 single process → in-memory đủ.

---

## Thứ tự implement (gợi ý)

1. **C5** observability — làm đầu tiên để đo baseline trước/sau mỗi fix.
2. **C1** parallel morning report — quick win, người dùng cảm nhận ngay.
3. **C6** rate limiter — bảo vệ LLM budget trước khi marketing.
4. **C4** DLQ — cần khi traffic tăng, failure pattern visible.
5. **C3** Redis queue — chỉ khi multi-process / multi-node.
6. **C2** batch LLM — re-evaluate xem Gmail còn không; nếu còn thì làm.

---

## Risk & rollback

| Rủi ro | Mitigation | Rollback |
|---|---|---|
| C1 semaphore quá cao → Telegram 429 | Bắt đầu với 10, tăng dần theo dõi 429 rate | Giảm semaphore concurrency |
| C3 ARQ/Celery break existing flow | Feature flag `USE_REDIS_QUEUE`, dual-write trong 1 tuần | Tắt flag, fallback asyncio |
| C5 OpenTelemetry overhead | Sample rate 10% production, 100% staging | Tắt SDK qua env |
| C6 false positive block legit user | Whitelist owner_telegram_id; log mọi block | Raise limit tạm thời |

---

## Liên quan

- Phase A (đã hoàn thành): `docs/archive/scaling-refactor-A.md`
- Phase B (đã hoàn thành): `docs/archive/scaling-refactor-B.md`
- Layer contract: `CLAUDE.md` §0.1
