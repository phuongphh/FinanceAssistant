# Scaling Refactor — Phase B (Cleanup layers)

> **STATUS: ✅ IMPLEMENTED (archived 2026-04-28).**
> Cả 5 fix đã merge:
> - B1 commit boundary — services có tag `TRANSACTION_OWNED_BY_CALLER`,
>   guard test `backend/tests/test_service_boundary.py`.
> - B2 duplicate user lookup — `backend/tests/test_handler_boundary.py`.
> - B3 Notifier port — `backend/ports/notifier.py`,
>   `backend/adapters/telegram_notifier.py`,
>   `backend/services/morning_report_service.py:18,227`.
> - B4 cache key per `user_id` + `shared_cache` — `llm_service.py:34`,
>   `backend/tests/test_llm_cache_isolation.py`.
> - B5 composite indexes — migration `e4f5a6b7c8d9`.
> Section "Sau Phase B — những gì còn lại cho Phase C" đã chuyển thành
> doc riêng: `docs/current/scaling-refactor-C.md`.
>
> **Mục tiêu:** Code không drift khi codebase/team lớn. Ranh giới layer rõ để issue Phase 2 tiếp theo không đi lạc.
> **Thời gian:** 3-4 ngày. **Blocks:** Bất kỳ issue Phase 2 mới nào.
> **Tiền đề:** Giai đoạn A đã merge — webhook đã có background worker, nên layer boundary mới có chỗ áp vào.

---

## Vấn đề đang gây drift

| # | Hiện trạng | Nguồn gốc | Chi phí tương lai |
|---|---|---|---|
| B1 | `db.commit()` rải rác trong services | `onboarding_service`, `dashboard_service`, `milestone_service` | Partial commit khi multi-step flow lỗi giữa chừng |
| B2 | Duplicate `_get_user_by_telegram_id` trong handlers | `callbacks.py:53-60` vs `dashboard_service` | Bug drift — giống bug đã fix ở `onboarding_service` |
| B3 | Services gửi Telegram trực tiếp | `morning_report_service.py:221,232,239` | Không test được service mà không mock HTTP; khi chuyển sang job queue sẽ kẹt |
| B4 | Cache LLM thiếu `user_id` trong key | `llm_service.py:73-74` `hash(prompt)` | User A và User B cùng prompt → chung cache entry; nguy hiểm khi prompt nhúng data user |
| B5 | Composite index cho query phổ biến chưa có | `goals(user_id, is_active, deleted_at)`, `income_records(user_id, deleted_at)` | < 10K users OK, > 10K scan toàn bảng |

---

## Kiến trúc target — Layer contract

Sau Phase A, runtime path đã là:
```
webhook → claim → background worker → handler → service → db/llm/telegram
```

Phase B cứng hóa **contract của từng layer**, không rewrite:

| Layer | ĐƯỢC làm | KHÔNG được làm |
|---|---|---|
| `routers/` | Parse HTTP, verify auth, enqueue, trả 200 | Commit DB, call LLM, business logic |
| `workers/` | Open session, dispatch, `commit()` một lần ở boundary | Business logic |
| `bot/handlers/` | Route intent, extract Telegram data, gọi service, format response | Commit DB, query DB trực tiếp (trừ view-only) |
| `services/` | Business logic thuần, nhận `db`, **flush only**, return domain objects | `commit()`, gọi Telegram, tạo LLM client, đọc env |
| `adapters/` (đổi tên từ `services/telegram_service.py`, `notion_sync.py`) | Transport: Telegram, Notion, DeepSeek, Claude | Business logic |

**Ports & adapters rút gọn:**
- `ports/notifier.py` — interface `Notifier.send_message(chat_id, text)`, `send_menu(...)`. Domain services nhận `Notifier` qua DI, test bằng fake.
- `ports/llm.py` — interface `LLM.call(prompt, task_type, user_id, ...)`. Service gọi port, không import OpenAI SDK trực tiếp.

Không làm full DI framework — Phase 0 dùng function arguments hoặc module-level singletons được thay ở test.

---

## B1 — Gom `db.commit()` về boundary

### Nguyên tắc
**Services flush, routers/workers commit.** Một request = một transaction.

### Cách tiếp cận (b) — migrate dần, không big-bang
Đã thống nhất: giữ `db.commit()` cũ trong services không break, thêm convention mới cho code mới, migrate incrementally.

### Bước 1: `@transactional` decorator
```python
# backend/shared/transactional.py
def transactional(fn):
    """Decorator for worker/router handlers that own the transaction boundary.

    - Passes `db` session explicitly (already injected by FastAPI or worker).
    - Commits on success, rolls back on exception.
    - Services called inside MUST NOT call db.commit() (but legacy ones still work
      idempotently — committing twice is a no-op on async session).
    """
    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        db: AsyncSession = kwargs.get("db") or _find_db_in_args(args)
        try:
            result = await fn(*args, **kwargs)
            await db.commit()
            return result
        except Exception:
            await db.rollback()
            raise
    return wrapper
```

**Lưu ý:** `get_db()` đã commit ở `yield` block (`database.py:58`). Sau khi add `@transactional`, chỉ dùng ở workers (mở session thủ công). Với routers, giữ nguyên `get_db()` commit — không duplicate layer.

### Bước 2: Migration checklist (per-service)
Đánh dấu services bằng docstring tag `# TRANSACTION_OWNED_BY_CALLER` sau khi migrate:

- [ ] `onboarding_service.step_3_ask_goal` — xóa `db.commit()`, caller commit
- [ ] `onboarding_service.set_primary_goal` — xóa
- [ ] `onboarding_service.set_step` — xóa
- [ ] `dashboard_service.get_or_create_user` — xóa (caller: webhook `/start`)
- [ ] `milestone_service.mark_milestone_reached` — xóa
- [ ] `expense_service.create_expense` — kiểm tra, xóa nếu có
- [ ] `goal_service.*` — audit
- [ ] `income_service.*` — audit

Mỗi service di chuyển = 1 commit, test theo. Không batch.

### Bước 3: Test guard
Thêm unit test `tests/shared/test_services_do_not_commit.py` grep code:
```python
def test_no_service_commits():
    for path in Path("backend/services").rglob("*.py"):
        source = path.read_text()
        # Allowed: # TRANSACTION_OWNED_BY_CALLER hoặc legacy whitelist
        if "TRANSACTION_OWNED_BY_CALLER" in source:
            continue
        if path.name in LEGACY_ALLOWLIST:
            continue
        assert "db.commit()" not in source, f"Service {path} still commits"
```
LEGACY_ALLOWLIST shrink dần mỗi PR. Zero khi migrate xong.

### Acceptance
- Flow onboarding step 3: set name + set goal + advance step → hoặc cả 3 thành công hoặc cả 3 rollback. Test bằng cách inject exception giữa `set_primary_goal` và `set_step`.

---

## B2 — Xóa duplicate user lookup

### Hiện trạng
`backend/bot/handlers/callbacks.py:53-60` có hàm local query users table. `dashboard_service.get_user_by_telegram_id` đã làm y hệt.

### Fix
1. Xóa hàm local trong `callbacks.py`.
2. Import `from backend.services.dashboard_service import get_user_by_telegram_id`.
3. Grep toàn repo cho pattern tương tự: `grep -rn "telegram_id ==" backend/bot/handlers/`.

### Test guard
Same pattern như B1 — unit test fail nếu handler có query raw `select(User).where(User.telegram_id ...)` ngoài service layer.

### Acceptance
- `rg "User.telegram_id" backend/bot/handlers/` → 0 matches.

---

## B3 — Notifier port

### Hiện trạng
`morning_report_service.py:221,232,239` gọi `send_message` trực tiếp từ `telegram_service`. Service domain (morning report logic) và transport (Telegram API) quyện vào nhau → không test pure, không dễ chuyển sang email/SMS sau.

### Kiến trúc target
```python
# backend/ports/notifier.py
class Notifier(Protocol):
    async def send_message(self, chat_id: int, text: str, **kwargs) -> bool: ...
    async def send_menu(self, chat_id: int) -> bool: ...

# backend/adapters/telegram_notifier.py
class TelegramNotifier:
    async def send_message(self, chat_id, text, **kw): ...  # calls telegram_service

# backend/adapters/fake_notifier.py  (for tests)
class FakeNotifier:
    def __init__(self): self.sent = []
    async def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text)); return True
```

### Wiring (Phase 0 — không full DI)
```python
# backend/services/notifier_provider.py
_notifier: Notifier | None = None

def get_notifier() -> Notifier:
    global _notifier
    if _notifier is None:
        _notifier = TelegramNotifier()
    return _notifier

def set_notifier(n: Notifier):  # for tests
    global _notifier
    _notifier = n
```

Services gọi `notifier = get_notifier(); await notifier.send_message(...)`. Test dùng `set_notifier(FakeNotifier())` ở fixture.

### Migration list
- `morning_report_service` — 3 call site
- `gmail_poller` — nếu có push notification khi có expense mới
- `milestone_service` — khi send celebration
- `monthly_report job` — khi push full report

### Rename `telegram_service` → `adapters/telegram.py`
Giữ alias một thời gian:
```python
# backend/services/telegram_service.py
from backend.adapters.telegram import *  # noqa — alias for back-compat
```
Xóa sau khi tất cả import đã update (1 PR cleanup cuối).

### Acceptance
- Unit test cho `morning_report_service` chạy không mock HTTP, dùng `FakeNotifier`, assert nội dung message.
- `rg "from backend.services.telegram_service import" backend/services/` → 0 matches (chỉ còn trong adapters).

---

## B4 — Cache LLM key thêm `user_id`

### Hiện trạng
`llm_service.py:73`:
```python
cache_key = f"{task_type}:{prompt_hash}"
```
`prompt_hash = sha256(prompt)`. Nếu prompt là `"Phân loại: merchant=Highland"` → mọi user cùng nhận kết quả cache, OK cho **categorization** vì không có PII.

Nhưng các prompt tương lai sẽ nhúng `display_name`, `monthly_income`, `goal_name` của user → user A cache kết quả chứa tên user A, user B query cùng merchant + context khác sẽ trúng nhầm cache của A.

### Fix
```python
# backend/services/llm_service.py
async def call_llm(
    prompt: str,
    task_type: str,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,   # ← mới
    use_cache: bool = True,
    shared_cache: bool = False,    # ← mới, explicit opt-in cho prompt không PII
) -> str:
    prompt_hash = _hash_prompt(prompt)
    if shared_cache:
        cache_key = f"shared:{task_type}:{prompt_hash}"
    else:
        uid_part = str(user_id) if user_id else "anon"
        cache_key = f"{task_type}:{uid_part}:{prompt_hash}"
    ...
```

### Ai dùng `shared_cache=True`?
- `categorize_expense` — prompt chỉ có merchant + amount, không có user data. Cache chia sẻ OK.
- Mọi task khác default `shared_cache=False` — an toàn trước.

### Migration
- Thêm 2 params mới, default không break callers hiện tại.
- Sửa `categorize_expense` set `shared_cache=True` để giữ cache hit rate.
- Audit mọi `call_llm` call site → thêm `user_id=user.id` khi có context user.

### Test
- Cùng prompt, user_id khác → 2 cache entry.
- Cùng prompt, `shared_cache=True` → 1 cache entry chia sẻ.

### Acceptance
- Grep `call_llm(` tất cả call site → mỗi call hoặc có `user_id=` hoặc có `shared_cache=True` (lint test).

---

## B5 — Composite index cho query phổ biến

### Index cần thêm
```sql
-- Migration: alembic revision
CREATE INDEX idx_goals_user_active ON goals(user_id, is_active, deleted_at)
    WHERE deleted_at IS NULL AND is_active = true;

CREATE INDEX idx_income_user_active ON income_records(user_id, deleted_at)
    WHERE deleted_at IS NULL;

CREATE INDEX idx_expenses_user_month_cat ON expenses(user_id, month_key, category)
    WHERE deleted_at IS NULL;
```

Tất cả dùng `WHERE deleted_at IS NULL` (partial index) — tiết kiệm 20-30% size vì soft-deleted rows không đáng index.

### Validation
Chạy `EXPLAIN ANALYZE` trước và sau trên query hot path:
- `report_service.get_monthly_summary(user_id, month)` — expect `Index Scan` thay `Seq Scan`
- `dashboard_service.get_active_goals(user_id)` — expect sub-ms
- `goal_service.list_active(user_id)` — expect sub-ms

### Acceptance
- Query plan report trên production-like dataset (10K expenses, 100 goals, 50 income records) → tất cả query hot path dùng index.

---

## Thứ tự implement

Độc lập giữa các fix → có thể parallel, nhưng PR tách:

1. **B5** (indexes) — chỉ migration, zero code risk. Làm đầu tiên.
2. **B4** (cache key) — đổi function signature, default không break. Low risk.
3. **B2** (duplicate lookup) — xóa code chết. Low risk.
4. **B1** (commit migration) — N PR nhỏ, 1 service/PR. Cao risk nếu gộp.
5. **B3** (notifier port) — cần refactor 4-5 call sites, rename module. Làm cuối.

---

## Test strategy Phase B

| Loại test | Scope | File dự kiến |
|---|---|---|
| Guard | Services không `db.commit()` (allowlist shrink dần) | `tests/shared/test_no_service_commits.py` |
| Guard | Handlers không query DB raw | `tests/shared/test_no_raw_handler_queries.py` |
| Unit | Transactional decorator rollback on exception | `tests/shared/test_transactional.py` |
| Unit | Cache key isolation per user_id | `tests/services/test_llm_cache_isolation.py` |
| Unit | Notifier port — fake captures messages | `tests/services/test_morning_report_notifier.py` |
| Integration | Onboarding multi-step atomicity | `tests/integration/test_onboarding_rollback.py` |
| Perf | EXPLAIN ANALYZE hot queries sử dụng index | `tests/perf/test_query_plans.py` (smoke) |

---

## Risk & rollback

| Rủi ro | Mitigation | Rollback |
|---|---|---|
| B1 migrate service quên xóa commit → double commit | async session commit idempotent, tests fail | Chỉ revert commit xóa `db.commit()` |
| B3 rename module break import | Giữ alias `from ... import *` | Xóa alias theo checklist |
| B4 cache hit rate giảm đột ngột | `shared_cache=True` cho categorize giữ cache rate | Theo dõi `llm_cache` size + hit rate; nếu drop > 50% điều tra |
| B5 index CREATE khoá table lâu | Dùng `CREATE INDEX CONCURRENTLY` trong migration | Alembic revert drop index |

---

## Sau Phase B — những gì còn lại cho Phase C

| # | Fix | Tại sao để sau |
|---|---|---|
| C1 | Morning report gửi song song (asyncio.gather + rate limit) | Cần Notifier port (B3) xong trước |
| C2 | Batch LLM cho Gmail poll | Cần `shared_cache` pattern (B4) + port LLM (cleanup sau B3) |
| C3 | Redis + ARQ/Celery | Chỉ cần khi > 1K active users; Postgres queue đủ cho 1K |
| C4 | DLQ với exponential backoff | Hiện `status='failed'` là dead letter thủ công — đủ dùng ở < 1K |
| C5 | Observability: OpenTelemetry + metric webhook latency, LLM cost/user | Cần infra monitoring riêng |
| C6 | Rate limiter per-user | Cần Redis hoặc token bucket in-memory — Phase 1 VPS |
