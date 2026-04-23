# Scaling Refactor — Phase A (Stop-the-bleeding)

> **Mục tiêu:** Webhook Telegram không chết ở 1K users. 3 fix bắt buộc trước khi go-live Phase 1.
> **Thời gian:** 2-3 ngày. **Blocks:** Phase 1 go-live.
> **Không làm:** Không thêm Redis, không thay queue stack, không rewrite service layer.

---

## Vấn đề đang chặn scale

| # | Triệu chứng | Nguồn gốc | Blast radius ở 1K users |
|---|---|---|---|
| A1 | Expense tạo 2-3 lần | `routers/telegram.py` không dedup `update_id` | 1-3% traffic → data corruption |
| A2 | DB deadlock cascade buổi sáng | `database.py:19-22` pool_size=5, max_overflow=10 | Webhook + morning job tranh connection → 503 |
| A3 | Webhook timeout → Telegram retry spiral | `bot/handlers/message.py:82-87` `call_llm` chạy trước khi return 200 | 2-10s per message × 10 workers → hết slot sau vài chục concurrent |

Ba fix này độc lập về code change, có thể implement song song nhưng nên merge theo thứ tự A2 → A1 → A3 (A2 ít rủi ro nhất, A3 nhiều rủi ro nhất).

---

## A1 — Telegram `update_id` dedup

### Nguyên tắc
Telegram retry khi không nhận 200 trong ~60s hoặc khi mạng chập. Mỗi update có `update_id` duy nhất, monotonic per-bot. Dedup bằng cách record `update_id` trước khi xử lý, skip nếu đã thấy.

### Data model — table mới `telegram_updates`
```sql
CREATE TABLE telegram_updates (
    update_id       BIGINT PRIMARY KEY,            -- Telegram's monotonic ID
    received_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status          VARCHAR(20) NOT NULL DEFAULT 'processing',
    -- 'processing' | 'done' | 'failed'
    processed_at    TIMESTAMPTZ,
    error_message   TEXT,
    payload         JSONB NOT NULL                 -- Full update body, dùng replay/debug
);

CREATE INDEX idx_telegram_updates_status ON telegram_updates(status)
    WHERE status = 'processing';
CREATE INDEX idx_telegram_updates_received_at ON telegram_updates(received_at);
```

**Tại sao PK là `update_id` thô (không UUID):**
- Dedup là điểm chốt — PK conflict = đã duplicate, không cần query thêm.
- `INSERT ... ON CONFLICT (update_id) DO NOTHING RETURNING update_id` cho câu trả lời atomic.

### Router logic
```python
# backend/routers/telegram.py — pseudo-code, không phải code final
@router.post("/webhook")
async def telegram_webhook(request, db):
    _verify_webhook_request(request)
    data = await request.json()
    update_id = data.get("update_id")
    if update_id is None:
        return {"ok": True}  # Malformed update — ignore, don't crash

    # Atomic claim
    claimed = await _claim_update(db, update_id, data)
    if not claimed:
        logger.info("Duplicate update_id=%s skipped", update_id)
        return {"ok": True}

    # Enqueue for background processing (see A3)
    asyncio.create_task(_process_update_safely(update_id, data))
    return {"ok": True}
```

`_claim_update` dùng `INSERT ... ON CONFLICT DO NOTHING` — nếu `rowcount == 0` → duplicate, skip. Nếu `== 1` → ta vừa claim, tiếp tục.

### Failure modes
- **Crash giữa chừng:** status vẫn là `processing`. Lifespan hook (startup) scan `status='processing'` cũ > 5 phút → re-enqueue (xem A3).
- **Retention:** Giữ 30 ngày rồi xóa qua job dọn rác. Ở 1K users × 20 updates/ngày × 30 = 600K rows — index trên `received_at` đủ nhanh.

### Acceptance
1. Gửi 2 request webhook với cùng `update_id` → chỉ 1 expense được tạo, lần 2 trả 200 với log `Duplicate ... skipped`.
2. Restart server giữa lúc đang process → row stuck `processing` → startup hook phát hiện và retry.
3. Unit test: `_claim_update` concurrent call → chỉ 1 thắng (giả lập bằng 2 session đồng thời).

---

## A2 — Connection pool tuning

### Nguyên tắc
Connection pool phải tỉ lệ với (số worker × concurrency per worker × tỉ lệ blocking I/O). Default 5+10 chỉ đủ cho dev đơn luồng.

### Tính toán target
- 4 uvicorn workers (Mac Mini 4 cores) × ~25 concurrent requests cho webhook async = peak 100 DB session claim.
- Morning report job: 1K users × 1 session/user, nhưng burst trong 1 phút (sau khi refactor A3 sang background).
- PostgreSQL default `max_connections=100` — không đủ. Phase 1 VPS nâng lên `max_connections=200`.

**Settings target:**
```python
pool_size=20,           # Steady-state connections
max_overflow=30,        # Burst capacity → total 50 per process
pool_timeout=10,        # Đợi connection max 10s rồi raise
pool_recycle=1800,      # Reset connection sau 30 phút (tránh stale qua PgBouncer)
pool_pre_ping=True,     # Ping trước mỗi checkout — phát hiện dead connection
```

4 workers × 50 = 200 connections peak → match `max_connections=200` của Postgres.

### Env-configurable
Tất cả giá trị trên đọc từ env qua `config.py`:
```python
class Settings(BaseSettings):
    db_pool_size: int = 20
    db_max_overflow: int = 30
    db_pool_timeout: int = 10
    db_pool_recycle: int = 1800
    db_pool_pre_ping: bool = True
```
Phase 0 (Mac Mini, 1 user) có thể override về `5/10` qua `.env`. Phase 1 VPS giữ default.

### Migration
1. Update `backend/database.py` — truyền tham số từ settings.
2. Update `.env.example` với 5 biến mới.
3. Update `docker-compose.yml` — thêm `command: postgres -c max_connections=200` cho service postgres.

### Acceptance
1. Load test 100 concurrent webhook requests → không có `TimeoutError: QueuePool limit`.
2. Kill connection thủ công ở Postgres → request tiếp theo vẫn thành công (pool_pre_ping reconnect).
3. `SELECT count(*) FROM pg_stat_activity` ở peak < pool_size + max_overflow.

---

## A3 — LLM ra khỏi webhook hot path

### Nguyên tắc
Webhook route chỉ làm 3 việc: verify → claim update_id → enqueue. Mọi work tốn >100ms (LLM call, Gmail sync) chạy trong background task, reuse process.

### Chọn (a) `asyncio.create_task` + task table — không thêm Redis
Lý do: <1K users dùng asyncio đủ. Khi cần scale lên 10K sẽ chuyển sang Redis+ARQ/Celery (Phase C), migration path rõ ràng vì đã có `telegram_updates` table đóng vai trò queue.

### Tách layer
```
routers/telegram.py          — verify + claim + enqueue (≤100ms)
     ↓ asyncio.create_task
workers/telegram_worker.py   — route_update(data) → dispatch to handlers
     ↓
bot/handlers/*.py            — existing code (message, callbacks, onboarding)
     ↓
services/*.py                — pure business logic (B phase cleans commits)
```

### `route_update()` extraction
Di chuyển toàn bộ logic xử lý message/callback từ `telegram_webhook` vào hàm thuần `route_update(db, data)`:
```python
# backend/workers/telegram_worker.py
async def route_update(data: dict) -> None:
    """Dispatch a Telegram update to the right handler.
    Opens its own DB session — webhook's session already closed."""
    async with get_session_factory()() as db:
        try:
            await _route(db, data)
            await db.commit()
            await _mark_done(db, data["update_id"])
        except Exception as e:
            await db.rollback()
            await _mark_failed(db, data["update_id"], str(e))
            logger.exception("route_update failed: update_id=%s", data.get("update_id"))
```

Quan trọng: **worker mở session mới**, không reuse session của webhook route (đã đóng khi `return {"ok": True}`).

### `_process_update_safely` wrapper
```python
async def _process_update_safely(update_id: int, data: dict) -> None:
    """Never-raise wrapper for background task — logs but does not crash event loop."""
    try:
        await route_update(data)
    except Exception:
        logger.exception("Background processing crashed for update_id=%s", update_id)
```

### Startup recovery (orphan task pickup)
Khi process restart, các update `status='processing'` > 5 phút chưa xong → mồ côi.
```python
# backend/main.py — lifespan
@asynccontextmanager
async def lifespan(app):
    await _recover_orphaned_updates()
    yield

async def _recover_orphaned_updates() -> None:
    cutoff = datetime.utcnow() - timedelta(minutes=5)
    async with get_session_factory()() as db:
        stmt = select(TelegramUpdate).where(
            TelegramUpdate.status == "processing",
            TelegramUpdate.received_at < cutoff,
        ).limit(100)
        orphans = (await db.execute(stmt)).scalars().all()
        for orphan in orphans:
            asyncio.create_task(_process_update_safely(orphan.update_id, orphan.payload))
        logger.info("Recovered %d orphaned updates", len(orphans))
```
Cap 100 để tránh overload sau khi down lâu.

### Graceful shutdown
Uvicorn SIGTERM → FastAPI lifespan `finally` block:
```python
# Wait up to 30s for in-flight background tasks
pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
if pending:
    logger.info("Waiting for %d background tasks to finish", len(pending))
    await asyncio.wait(pending, timeout=30)
```
Nếu task chưa xong trong 30s, shutdown vẫn proceed — lần khởi động sau startup hook sẽ recover.

### Cái KHÔNG làm ở giai đoạn A
- Không dùng Celery/RQ — để Phase C.
- Không thay PostgreSQL bằng Redis queue — Postgres đủ cho 1K users.
- Không migrate tất cả `call_llm` sang background — chỉ path webhook. Scheduled jobs (morning_report, gmail_poller) vẫn chạy như hiện tại, giai đoạn B mới chuyển.

### Acceptance
1. Webhook response time p95 < 150ms (đo bằng middleware timing) — trước fix là 2-10s.
2. Gửi 50 message đồng thời qua Telegram → tất cả được reply, không có timeout.
3. Kill process giữa lúc đang process 5 updates → restart → 5 updates đó được retry (kiểm tra `telegram_updates.status`).
4. Integration test: webhook trả 200 trong <200ms kể cả khi mock LLM sleep 5s.

---

## Thứ tự implement

Task theo thứ tự để minimize rollback risk:

1. **A2** (env-configurable pool) — Đổi config, không đổi logic. Rollback = đổi env back.
2. **A1** (update_id dedup) — Thêm table + migration + router logic. Rollback = drop table + revert router.
3. **A3** (background processing) — Refactor router + thêm worker + recovery hook. Rollback = revert PR.

Mỗi bước 1 PR riêng. PR A3 phụ thuộc A1 (cần `telegram_updates` table để track status).

---

## Test strategy Phase A

| Loại test | Scope | File dự kiến |
|---|---|---|
| Unit | `_claim_update` atomicity, `_hash_prompt` unchanged | `tests/routers/test_telegram_dedup.py` |
| Unit | `_recover_orphaned_updates` picks up stale rows | `tests/workers/test_recovery.py` |
| Integration | Webhook trả 200 trong <200ms với LLM mock sleep | `tests/integration/test_webhook_timing.py` |
| Integration | Duplicate `update_id` chỉ tạo 1 expense | `tests/integration/test_dedup_e2e.py` |
| Load | 100 concurrent webhook → không có pool exhaustion | Manual, locust script |

---

## Risk & rollback

| Rủi ro | Mitigation | Rollback |
|---|---|---|
| Background task crash nuốt lỗi | `_process_update_safely` log + `telegram_updates.status='failed'` | Xem `status='failed'` trong DB, replay thủ công |
| Pool tuning sai → Postgres từ chối | Tăng `max_connections` Postgres trước khi deploy app | `.env` rollback |
| Race: webhook claim rồi crash trước khi spawn task | Startup recovery pickup sau 5 phút | Manual `UPDATE telegram_updates SET status='processing' WHERE update_id=?` để force retry |
| Orphan recovery storm sau outage dài | `limit(100)` + 5 phút cutoff | Tăng cutoff nếu cần, chạy thủ công |

---

## Không giải quyết ở giai đoạn A (để giai đoạn B/C)

- `db.commit()` trong services → giai đoạn B
- Cache LLM thiếu `user_id` → giai đoạn B
- Morning report gửi tuần tự → giai đoạn C (cần concurrency primitive proper)
- Batch LLM cho Gmail poll → giai đoạn C
- DLQ proper với exponential backoff → giai đoạn C (hiện `status='failed'` là DLQ đơn giản)
