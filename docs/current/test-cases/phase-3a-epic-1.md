# Phase 3A — Epic 1 Test Cases

> **Epic:** Asset Data Model & Manual Entry (Tuần 1)
> **Goal:** User nhập được 5 loại asset (cash, stock, real_estate, crypto, gold), xem tổng net worth tính đúng.
> **Issues covered:** P3A-1 → P3A-9
> **Reference:** [`phase-3a-issues.md`](../phase-3a-issues.md) · [`phase-3a-detailed.md`](../phase-3a-detailed.md) §1.1–§1.7

---

## 📋 Cách dùng file này

- Mỗi issue có 2 nhóm test: **Happy Path** (golden flow) + **Corner Cases** (edge / lỗi / bảo mật).
- Mỗi test có format: **ID** · **Mục tiêu** · **Bước thực hiện** · **Kết quả mong đợi** · **Maps to AC** (acceptance criteria).
- Cuối file: bảng map ngược về **Checklist Cuối Tuần 1** (`phase-3a-detailed.md` line 1003–1015).
- Test thủ công qua: (a) `psql` cho DB, (b) `pytest` cho service, (c) Telegram bot cho wizard, (d) curl cho API.

### Pre-test setup chung

```bash
# 1. PostgreSQL + Redis chạy
docker-compose up -d postgres redis

# 2. Apply migrations sạch
alembic downgrade base && alembic upgrade head

# 3. Seed user test (telegram_id = 999000001)
psql $DATABASE_URL -c "INSERT INTO users (id, telegram_id, display_name, monthly_income) VALUES (gen_random_uuid(), 999000001, 'Test User', 20000000);"

# 4. Lấy user_id để dùng cho các test
export TEST_USER_ID=$(psql $DATABASE_URL -tAc "SELECT id FROM users WHERE telegram_id=999000001;")
```

---

# P3A-1 — Database Migrations (assets, snapshots, income_streams, users wealth fields)

**Maps to AC:** migration files apply, columns + indexes đúng, downgrade chạy được.

## Happy Path

### TC-1.1.H1 — Apply 4 migrations forward thành công
- **Mục tiêu:** Verify cả 4 migrations chạy không lỗi từ base.
- **Bước:**
  1. `alembic downgrade base`
  2. `alembic upgrade head`
  3. `alembic current` — xem revision cuối.
- **Kết quả mong đợi:**
  - Không có exception.
  - `alembic current` show revision của migration cuối cùng (add_user_wealth_fields).
  - `\dt` trong psql liệt kê được: `assets`, `asset_snapshots`, `income_streams`.

### TC-1.1.H2 — Schema `assets` đầy đủ columns + types đúng
- **Bước:** `psql $DATABASE_URL -c "\d assets"`
- **Kết quả mong đợi:**
  - Columns: `id` (uuid PK), `user_id` (uuid NOT NULL FK→users), `asset_type` (varchar NOT NULL), `subtype` (varchar), `name` (varchar NOT NULL), `description` (text), `initial_value` (numeric(20,2) NOT NULL), `current_value` (numeric(20,2) NOT NULL), `acquired_at` (date NOT NULL), `last_valued_at` (timestamptz), `metadata` (jsonb), `is_active` (bool default true), `sold_at` (date), `sold_value` (numeric(20,2)), `created_at`, `updated_at` (timestamptz).
  - **Money columns phải là `numeric`, KHÔNG phải `float` / `double precision`.**

### TC-1.1.H3 — Schema `asset_snapshots` + UNIQUE(asset_id, snapshot_date)
- **Bước:** `\d asset_snapshots`
- **Kết quả mong đợi:**
  - Columns: `id` (bigserial PK), `asset_id` (uuid FK), `user_id` (uuid FK), `snapshot_date` (date NOT NULL), `value` (numeric(20,2)), `source` (varchar), `created_at`.
  - Unique constraint trên `(asset_id, snapshot_date)`.

### TC-1.1.H4 — Schema `income_streams`
- **Bước:** `\d income_streams`
- **Kết quả mong đợi:** columns `source_type` (varchar NOT NULL: salary/dividend/interest/rental/other), `name`, `amount_monthly` (numeric(15,2)), `is_active`, `metadata` (jsonb).

### TC-1.1.H5 — `users` table có wealth fields mới
- **Bước:** `\d users`
- **Kết quả mong đợi:** columns mới có mặt: `wealth_level` (varchar), `expense_threshold_micro` (int default 200000), `expense_threshold_major` (int default 2000000), `briefing_enabled` (bool default true), `briefing_time` (time default '07:00').

### TC-1.1.H6 — Indexes tạo đúng
- **Bước:**
  ```sql
  SELECT indexname FROM pg_indexes WHERE tablename IN ('assets', 'asset_snapshots', 'income_streams');
  ```
- **Kết quả mong đợi:** xuất hiện `idx_assets_user_active`, `idx_assets_type`, `idx_snapshots_user_date`, `idx_income_user_active`.

### TC-1.1.H7 — Downgrade rollback toàn bộ
- **Bước:**
  1. `alembic downgrade -4` (lùi 4 migration).
  2. `\dt` trong psql.
- **Kết quả mong đợi:** 3 bảng `assets`, `asset_snapshots`, `income_streams` biến mất. Cột wealth bị xóa khỏi `users`. Không lỗi.

## Corner Cases

### TC-1.1.C1 — Money lưu numeric(20,2), không mất precision
- **Bước:**
  ```sql
  INSERT INTO assets (id, user_id, asset_type, name, initial_value, current_value, acquired_at)
  VALUES (gen_random_uuid(), :user_id, 'cash', 'precision-test', 12345678901234.56, 12345678901234.56, CURRENT_DATE);
  SELECT current_value FROM assets WHERE name='precision-test';
  ```
- **Kết quả mong đợi:** Trả về **đúng** `12345678901234.56` — không round, không lệch float.

### TC-1.1.C2 — `user_id` NOT NULL enforce
- **Bước:** Insert asset không có user_id.
- **Kết quả mong đợi:** Postgres raise `null value in column "user_id" violates not-null constraint`.

### TC-1.1.C3 — FK cascade khi user bị xóa cứng (nếu schema dùng CASCADE)
- **Bước:** Tạo asset cho user A, `DELETE FROM users WHERE id = :user_a_id`.
- **Kết quả mong đợi:**
  - Nếu spec là `ON DELETE CASCADE`: assets + snapshots + income_streams của user A bị xóa theo.
  - Nếu spec là `ON DELETE RESTRICT`: query bị reject. **Document rõ behavior nào được chọn** — đừng để mơ hồ.

### TC-1.1.C4 — UNIQUE(asset_id, snapshot_date) chặn duplicate
- **Bước:** Insert 2 snapshot với cùng `asset_id` + cùng `snapshot_date`.
- **Kết quả mong đợi:** Lần insert thứ 2 raise `duplicate key value violates unique constraint`.

### TC-1.1.C5 — JSONB metadata accept nested
- **Bước:**
  ```sql
  INSERT INTO assets (..., metadata) VALUES (..., '{"ticker":"VNM","quantity":100,"nested":{"a":1}}');
  SELECT metadata->>'ticker', metadata->'nested'->>'a' FROM assets WHERE ...;
  ```
- **Kết quả mong đợi:** Query JSON path hoạt động.

### TC-1.1.C6 — Default values của users wealth fields
- **Bước:** Insert user mới chỉ với telegram_id, query lại.
- **Kết quả mong đợi:**
  - `expense_threshold_micro = 200000`
  - `expense_threshold_major = 2000000`
  - `briefing_enabled = true`
  - `briefing_time = '07:00:00'`

### TC-1.1.C7 — Re-apply migration không lỗi (idempotent)
- **Bước:** Sau `upgrade head` thành công, chạy lại `alembic upgrade head`.
- **Kết quả mong đợi:** No-op, không exception.

### TC-1.1.C8 — Downgrade từng step độc lập
- **Bước:** `upgrade head` → `downgrade -1` → `upgrade head` → `downgrade -1` → `upgrade head`.
- **Kết quả mong đợi:** Mỗi step pass, không leak object (kiểm tra `\dt` sau mỗi step).

### TC-1.1.C9 — Negative value không bị reject ở DB layer (validate ở service)
- **Bước:** Insert raw `current_value = -1000`.
- **Kết quả mong đợi:** DB **cho phép** (numeric không có CHECK constraint mặc định) — note rằng validation âm số là trách nhiệm của service layer (P3A-3, P3A-6). Nếu spec yêu cầu `CHECK (current_value >= 0)` thì test ngược lại.

### TC-1.1.C10 — Index `idx_snapshots_user_date` ordering DESC
- **Bước:** `\d+ idx_snapshots_user_date` hoặc `pg_indexes` query.
- **Kết quả mong đợi:** Index có `snapshot_date DESC` — quan trọng cho `calculate_historical()` query (DISTINCT ON performance).

---

# P3A-2 — Asset / AssetSnapshot / IncomeStream Models + asset_categories.yaml

**Maps to AC:** SQLAlchemy models, AssetType enum, YAML categories, helper functions, unit tests.

## Happy Path

### TC-1.2.H1 — Import models không lỗi
- **Bước:** `python -c "from app.wealth.models.asset import Asset; from app.wealth.models.asset_snapshot import AssetSnapshot; from app.wealth.models.income_stream import IncomeStream; print('OK')"`
- **Kết quả mong đợi:** Print `OK`, không ImportError, không circular import.

### TC-1.2.H2 — `AssetType` enum có đủ 6 values
- **Bước:** `python -c "from app.wealth.models.asset_types import AssetType; print([e.value for e in AssetType])"`
- **Kết quả mong đợi:** Output chứa đúng 6: `['cash', 'stock', 'real_estate', 'crypto', 'gold', 'other']`.

### TC-1.2.H3 — Create + read Asset qua ORM
- **Bước:** Trong pytest hoặc REPL async:
  ```python
  asset = Asset(user_id=USER_ID, asset_type='cash', name='VCB', initial_value=Decimal('100000000'),
                current_value=Decimal('100000000'), acquired_at=date.today())
  session.add(asset); await session.flush()
  fetched = await session.get(Asset, asset.id)
  ```
- **Kết quả mong đợi:** `fetched.name == 'VCB'`, `fetched.current_value == Decimal('100000000')` (Decimal, not float).

### TC-1.2.H4 — Update Asset + `updated_at` thay đổi
- **Bước:** Sửa `asset.current_value`, flush, đọc lại.
- **Kết quả mong đợi:** `updated_at` mới > `created_at`.

### TC-1.2.H5 — Relationship Asset ↔ AssetSnapshot
- **Bước:** Tạo Asset + 2 AssetSnapshot trỏ về cùng asset_id; query `asset.snapshots`.
- **Kết quả mong đợi:** Trả về list 2 snapshot, sắp xếp được theo `snapshot_date`.

### TC-1.2.H6 — Hybrid property `gain_loss`
- **Bước:** Asset với `initial_value=100tr`, `current_value=120tr`. Đọc `asset.gain_loss`.
- **Kết quả mong đợi:** `Decimal('20000000')`. Test với current < initial cho âm số.

### TC-1.2.H7 — `asset_categories.yaml` có đủ 6 loại
- **Bước:**
  ```python
  import yaml
  data = yaml.safe_load(open('content/asset_categories.yaml'))
  assert set(data['asset_types'].keys()) == {'cash','stock','real_estate','crypto','gold','other'}
  ```
- **Kết quả mong đợi:** Pass. Mỗi loại có `icon`, `label_vi`, `subtypes`, `required_fields`.

### TC-1.2.H8 — Helper `get_asset_config('stock')`
- **Bước:**
  ```python
  from app.wealth.models.asset_types import get_asset_config
  cfg = get_asset_config('stock')
  ```
- **Kết quả mong đợi:** Dict có `icon='📈'`, `label_vi='Chứng khoán'`, `required_fields` chứa `ticker`, `quantity`, `initial_value`.

### TC-1.2.H9 — Helper `get_subtypes('cash')`
- **Bước:** `get_subtypes('cash')`
- **Kết quả mong đợi:** Trả về dict/list chứa `bank_savings`, `bank_checking`, `cash`, `e_wallet` với label tiếng Việt.

### TC-1.2.H10 — IncomeStream model basic CRUD
- **Bước:** Tạo IncomeStream salary 20tr/tháng, lưu, đọc lại.
- **Kết quả mong đợi:** `amount_monthly == Decimal('20000000')`, `source_type == 'salary'`, `is_active == True`.

## Corner Cases

### TC-1.2.C1 — `asset_type` ngoài enum bị reject
- **Bước:** Tạo Asset với `asset_type='invalid_xyz'`.
- **Kết quả mong đợi:**
  - Nếu cột là Postgres ENUM type: raise lỗi DB.
  - Nếu là VARCHAR + Python validation: raise `ValueError` ở model layer.
  - **Phải fail somewhere** — không silently lưu rác.

### TC-1.2.C2 — `current_value` default = `initial_value` khi không truyền
- **Bước:** Tạo Asset chỉ truyền `initial_value=50tr`, không có `current_value`.
- **Kết quả mong đợi:** Sau flush, `current_value == Decimal('50000000')`. (Logic này có thể nằm ở service, nhưng test cả 2 layers.)

### TC-1.2.C3 — Money field là Decimal, không bị cast về float
- **Bước:**
  ```python
  asset = await session.get(Asset, asset_id)
  assert isinstance(asset.current_value, Decimal)
  assert not isinstance(asset.current_value, float)
  ```
- **Kết quả mong đợi:** Pass. **Critical** — float làm sai cộng tiền.

### TC-1.2.C4 — Metadata JSON empty + null vs `{}`
- **Bước:** Tạo 2 asset: một với `metadata=None`, một với `metadata={}`.
- **Kết quả mong đợi:** Cả 2 đọc lại đều ok (None hoặc {} đều acceptable, nhưng phải consistent — document rõ).

### TC-1.2.C5 — Metadata với key tiếng Việt có dấu
- **Bước:** `metadata={"địa_chỉ": "Hà Nội", "diện_tích": 80}`. Lưu, đọc lại.
- **Kết quả mong đợi:** Round-trip giữ đúng UTF-8, query JSON path `metadata->>'địa_chỉ'` trả về `'Hà Nội'`.

### TC-1.2.C6 — Subtype không thuộc asset_type vẫn lưu được (nhưng cảnh báo)
- **Bước:** Tạo Asset `asset_type='cash'` nhưng `subtype='bitcoin'`.
- **Kết quả mong đợi:** DB cho phép (validation cross-field là việc của service). Nhưng `get_subtypes('cash')` không chứa 'bitcoin' → service nên reject. Document rõ ai validate.

### TC-1.2.C7 — YAML file thiếu / corrupt
- **Bước:** Đổi tên `content/asset_categories.yaml` → `.bak`, gọi `get_asset_config('cash')`.
- **Kết quả mong đợi:** Raise `FileNotFoundError` rõ ràng (không silent fail trả `{}`). **Quan trọng:** lỗi này phải bắt được sớm khi app start, không xảy ra runtime giữa user flow.

### TC-1.2.C8 — YAML có asset_type missing required key
- **Bước:** Sửa file YAML, xóa `icon` của cash. Reload.
- **Kết quả mong đợi:** Hoặc validation fail at load time, hoặc helper trả về default sane (`icon=''`). Không crash khi formatter render.

### TC-1.2.C9 — `get_asset_config('xyz_unknown')`
- **Bước:** `get_asset_config('not_exists')`
- **Kết quả mong đợi:** Trả về `{}` (theo code spec line 358) — **không** raise. Caller phải handle empty dict.

### TC-1.2.C10 — IncomeStream với `amount_monthly = 0`
- **Bước:** Tạo IncomeStream với `amount_monthly=Decimal('0')`.
- **Kết quả mong đợi:** Lưu được (user có thể có income source pause). Threshold service (P3A-16) sẽ default về 200k/2tr cho income=0.

### TC-1.2.C11 — Concurrent insert 2 asset cùng tên cùng user
- **Bước:** Async tạo song song 2 Asset cùng `name='VCB'`, cùng `user_id`.
- **Kết quả mong đợi:** Cả 2 đều lưu được (không có UNIQUE constraint trên name) — đúng theo spec. Document: user có thể có 2 TK VCB khác nhau.

### TC-1.2.C12 — Soft-delete fields default
- **Bước:** Tạo Asset, không truyền `is_active`, `sold_at`, `sold_value`.
- **Kết quả mong đợi:** `is_active=True`, `sold_at=None`, `sold_value=None`.

### TC-1.2.C13 — `last_valued_at` auto-set khi create
- **Bước:** Tạo Asset không truyền `last_valued_at`.
- **Kết quả mong đợi:** Tự động bằng `datetime.utcnow()` (theo spec line 414).

---

# P3A-3 — AssetService (CRUD + soft delete)

**Maps to AC:** create_asset, update_current_value, get_user_assets, get_asset_by_id, soft_delete, edge cases (current_value=None, multiple updates same day).

## Happy Path

### TC-1.3.H1 — `create_asset()` tạo asset + snapshot đầu tiên cùng lúc
- **Mục tiêu:** Verify một call duy nhất sinh ra cả Asset row và AssetSnapshot row.
- **Bước:**
  ```python
  svc = AssetService()
  asset = await svc.create_asset(
      user_id=USER_ID, asset_type='cash', subtype='bank_savings',
      name='VCB', initial_value=Decimal('100000000'),
  )
  snapshots = await session.execute(
      select(AssetSnapshot).where(AssetSnapshot.asset_id == asset.id)
  )
  ```
- **Kết quả mong đợi:**
  - `asset.id` là UUID, `asset.current_value == Decimal('100000000')`.
  - Có **đúng 1** AssetSnapshot với `snapshot_date = today`, `value = 100000000`, `source = 'user_input'` (hoặc theo spec).

### TC-1.3.H2 — `update_current_value()` create snapshot mới cho ngày khác
- **Bước:**
  1. Hôm nay: tạo asset 100tr (auto snapshot ngày 1).
  2. Mock `date.today()` → ngày 2 (hoặc backdate snapshot ngày 1).
  3. Gọi `svc.update_current_value(asset.id, USER_ID, Decimal('110000000'))`.
- **Kết quả mong đợi:**
  - `asset.current_value == 110000000`.
  - Có 2 snapshot: ngày 1 (100tr), ngày 2 (110tr).
  - `asset.last_valued_at` được update.

### TC-1.3.H3 — `get_user_assets()` mặc định chỉ trả active
- **Bước:** Tạo 3 asset (2 active, 1 đã `is_active=False`). Gọi `await svc.get_user_assets(USER_ID)`.
- **Kết quả mong đợi:** Trả về 2 asset, không chứa cái inactive.

### TC-1.3.H4 — `get_user_assets(include_inactive=True)` trả tất
- **Bước:** Như trên, thêm `include_inactive=True`.
- **Kết quả mong đợi:** Trả về cả 3 asset.

### TC-1.3.H5 — `get_asset_by_id()` happy path
- **Bước:** `await svc.get_asset_by_id(asset.id, USER_ID)`.
- **Kết quả mong đợi:** Trả về Asset object, đúng id.

### TC-1.3.H6 — `soft_delete()` không xóa cứng + giữ snapshots
- **Bước:**
  1. Tạo asset, có 3 snapshots.
  2. `await svc.soft_delete(asset.id, USER_ID, sold_value=Decimal('120000000'))`.
  3. Query lại bằng SQL trực tiếp.
- **Kết quả mong đợi:**
  - Asset row vẫn còn trong DB, `is_active=False`, `sold_at=today`, `sold_value=120000000`.
  - 3 snapshots cũ vẫn còn (KHÔNG bị cascade delete).

### TC-1.3.H7 — Service KHÔNG tự commit (theo layer contract)
- **Mục tiêu:** Verify service chỉ flush, caller sở hữu transaction (CLAUDE.md §0.1).
- **Bước:** Trong test, dùng session với `expire_on_commit=False`, không commit; rollback sau call. Verify không có row sót lại trong DB sau rollback.
- **Kết quả mong đợi:** Asset KHÔNG xuất hiện sau rollback → chứng tỏ service không tự gọi `db.commit()`.

## Corner Cases

### TC-1.3.C1 — `create_asset()` với `current_value=None` → default = `initial_value`
- **Bước:** `await svc.create_asset(..., initial_value=Decimal('50000000'), current_value=None)`.
- **Kết quả mong đợi:** `asset.current_value == Decimal('50000000')`. Snapshot đầu tiên cũng có `value = 50000000`.

### TC-1.3.C2 — Update value 2 lần cùng ngày → KHÔNG duplicate snapshot
- **Bước:**
  1. `create_asset(initial_value=100tr)` (auto snapshot today, value=100tr).
  2. Cùng ngày: `update_current_value(asset.id, USER_ID, 105tr)`.
  3. Cùng ngày: `update_current_value(asset.id, USER_ID, 110tr)`.
- **Kết quả mong đợi:**
  - Chỉ có **1** snapshot cho today.
  - Snapshot value = `110000000` (giá trị cuối cùng), KHÔNG phải 100tr hay 105tr.
  - UNIQUE(asset_id, snapshot_date) không raise conflict.

### TC-1.3.C3 — `get_asset_by_id()` cross-user → reject (security)
- **Bước:** User A tạo asset. User B gọi `get_asset_by_id(asset_id_of_A, USER_B_ID)`.
- **Kết quả mong đợi:** Raise `ValueError` (hoặc trả `None` rõ ràng — document chọn behavior nào). **KHÔNG** trả về Asset của user A. **Critical security test.**

### TC-1.3.C4 — `update_current_value()` cross-user → reject
- **Bước:** User A tạo asset. User B gọi update.
- **Kết quả mong đợi:** Raise `ValueError`. Asset của A KHÔNG bị thay đổi.

### TC-1.3.C5 — `soft_delete()` cross-user → reject
- **Bước:** User A tạo asset. User B gọi soft_delete.
- **Kết quả mong đợi:** Raise `ValueError`. Asset của A vẫn `is_active=True`.

### TC-1.3.C6 — `soft_delete()` asset đã inactive
- **Bước:** Soft-delete asset đã `is_active=False`.
- **Kết quả mong đợi:** Idempotent — không lỗi, hoặc raise rõ ràng "already deleted". Document chọn behavior nào.

### TC-1.3.C7 — `update_current_value()` với value âm
- **Bước:** `update_current_value(asset.id, USER_ID, Decimal('-1000000'))`.
- **Kết quả mong đợi:** Raise `ValueError("current_value must be >= 0")`. **Service phải validate** (DB không có CHECK — xem TC-1.1.C9).

### TC-1.3.C8 — `update_current_value()` với value = 0
- **Bước:** `update_current_value(asset.id, USER_ID, Decimal('0'))`.
- **Kết quả mong đợi:** Cho phép (asset mất giá hoàn toàn, hoặc TK rút sạch). Snapshot value=0.

### TC-1.3.C9 — `create_asset()` với `initial_value` âm hoặc 0
- **Bước:** `initial_value=Decimal('-100')` và `initial_value=Decimal('0')`.
- **Kết quả mong đợi:**
  - Âm: raise `ValueError`.
  - Zero: cho phép (edge case rare, nhưng không nên crash).

### TC-1.3.C10 — `get_user_assets()` với user không có asset nào
- **Bước:** User mới tạo, chưa có asset. `await svc.get_user_assets(NEW_USER_ID)`.
- **Kết quả mong đợi:** Trả về `[]` (empty list), KHÔNG raise, KHÔNG trả `None`.

### TC-1.3.C11 — `create_asset()` với `acquired_at` future date
- **Bước:** `acquired_at = date.today() + timedelta(days=30)`.
- **Kết quả mong đợi:** Document behavior — hoặc reject, hoặc cho phép (user kế hoạch). Nếu cho phép, snapshot vẫn ở `today`, không ở future.

### TC-1.3.C12 — `create_asset()` với metadata None vs empty dict
- **Bước:** Tạo asset với `metadata=None` và `metadata={}`. Đọc lại.
- **Kết quả mong đợi:** Cả 2 đều OK; service nên normalize về `{}` (theo spec line 411).

### TC-1.3.C13 — Concurrent update cùng asset cùng ngày (race condition)
- **Bước:** Async chạy 2 `update_current_value()` song song trên cùng asset.
- **Kết quả mong đợi:** Không raise UNIQUE violation; cuối cùng snapshot value = một trong 2 giá trị (last-write-wins acceptable). KHÔNG có 2 row cho cùng (asset_id, today).

### TC-1.3.C14 — `get_asset_by_id()` với UUID không tồn tại
- **Bước:** `get_asset_by_id(uuid4(), USER_ID)` (random UUID).
- **Kết quả mong đợi:** Trả về `None` hoặc raise `NotFoundError` rõ ràng. KHÔNG return một asset random.

### TC-1.3.C15 — Decimal precision không bị mất qua service
- **Bước:** `create_asset(initial_value=Decimal('123456789.99'))`. Đọc lại.
- **Kết quả mong đợi:** `asset.current_value == Decimal('123456789.99')` exact.

---

# P3A-4 — NetWorthCalculator

**Maps to AC:** `NetWorthBreakdown` + `NetWorthChange` dataclasses, `calculate()`, `calculate_historical()`, `calculate_change()`, edge cases (0 assets, no snapshots, just-created user), Decimal not float, DISTINCT ON performance.

## Happy Path

### TC-1.4.H1 — `calculate()` cộng đúng tổng + group by type
- **Bước:** Setup user có:
  - 2 cash: 50tr + 30tr = 80tr
  - 1 stock: 100tr
  - 1 gold: 20tr
- Gọi `await NetWorthCalculator().calculate(USER_ID)`.
- **Kết quả mong đợi:**
  - `result.total == Decimal('200000000')`.
  - `result.by_type == {'cash': Decimal('80000000'), 'stock': Decimal('100000000'), 'gold': Decimal('20000000')}`.
  - `result.asset_count == 4`.
  - `result.largest_asset` là asset stock 100tr.

### TC-1.4.H2 — `calculate()` chỉ tính active assets
- **Bước:** Setup 3 active (tổng 100tr) + 1 inactive (50tr). Gọi calculate.
- **Kết quả mong đợi:** `total == 100000000`. Asset inactive KHÔNG được cộng.

### TC-1.4.H3 — `calculate_historical()` lấy snapshot gần nhất ≤ target_date
- **Bước:** Asset có snapshots:
  - 2026-04-01: 100tr
  - 2026-04-15: 110tr
  - 2026-04-25: 120tr
- Gọi `calculate_historical(USER_ID, date(2026, 4, 20))`.
- **Kết quả mong đợi:** Trả về `Decimal('110000000')` (snapshot 04-15, là cái gần nhất ≤ 04-20).

### TC-1.4.H4 — `calculate_change(period='day')` đúng
- **Bước:** Net worth hôm qua 100tr, hôm nay 110tr. Gọi `calculate_change(USER_ID, 'day')`.
- **Kết quả mong đợi:**
  - `current == 110000000`, `previous == 100000000`.
  - `change_absolute == 10000000`.
  - `change_percentage == Decimal('10.00')` (10%, format theo spec).
  - `period_label == 'day'` (hoặc tương đương).

### TC-1.4.H5 — `calculate_change(period='week'|'month'|'year')` đều support
- **Bước:** Lần lượt gọi với 4 period values: `'day'`, `'week'`, `'month'`, `'year'`.
- **Kết quả mong đợi:** Cả 4 đều return `NetWorthChange` dataclass valid, KHÔNG raise.

### TC-1.4.H6 — `NetWorthBreakdown` là dataclass với đủ field
- **Bước:** Inspect type của result.
- **Kết quả mong đợi:** Có exact attrs: `total`, `by_type`, `asset_count`, `largest_asset`. Tất cả money là `Decimal`.

### TC-1.4.H7 — `NetWorthChange` là dataclass với đủ field
- **Bước:** Inspect.
- **Kết quả mong đợi:** Có `current`, `previous`, `change_absolute`, `change_percentage`, `period_label`. Money fields là `Decimal`.

## Corner Cases

### TC-1.4.C1 — User 0 assets → total=0, không crash
- **Bước:** User mới, chưa có asset. Gọi `calculate(USER_ID)`.
- **Kết quả mong đợi:**
  - `result.total == Decimal('0')`.
  - `result.by_type == {}`.
  - `result.asset_count == 0`.
  - `result.largest_asset is None`.
  - **KHÔNG raise**, KHÔNG ZeroDivisionError.

### TC-1.4.C2 — User 0 assets → `calculate_change()` không crash
- **Bước:** Gọi `calculate_change(USER_ID, 'month')`.
- **Kết quả mong đợi:**
  - `current == 0`, `previous == 0`, `change_absolute == 0`.
  - `change_percentage == 0` (KHÔNG ZeroDivisionError, KHÔNG NaN, KHÔNG `inf`).

### TC-1.4.C3 — User vừa tạo (chưa có snapshot lịch sử) → previous=0
- **Bước:** User tạo asset hôm nay. Hôm nay gọi `calculate_change(USER_ID, 'month')`.
- **Kết quả mong đợi:** `previous == 0` (không có snapshot 1 tháng trước), `change_absolute == current`. KHÔNG raise.

### TC-1.4.C4 — Tất cả money là `Decimal`, KHÔNG `float`
- **Bước:**
  ```python
  result = await calc.calculate(USER_ID)
  assert isinstance(result.total, Decimal)
  for v in result.by_type.values(): assert isinstance(v, Decimal)
  ```
- **Kết quả mong đợi:** Pass. **CRITICAL** theo CLAUDE.md §13.

### TC-1.4.C5 — `calculate_historical()` với date trước mọi snapshot
- **Bước:** Snapshots sớm nhất 2026-04-01. Query với `date(2026, 1, 1)`.
- **Kết quả mong đợi:** Trả về `Decimal('0')` (không có snapshot ≤ date này), KHÔNG raise.

### TC-1.4.C6 — `calculate_historical()` với date trong tương lai
- **Bước:** Query với `date.today() + timedelta(days=30)`.
- **Kết quả mong đợi:** Trả về snapshot mới nhất hiện tại (= current). Document behavior nếu khác.

### TC-1.4.C7 — `calculate_change(period='invalid')` 
- **Bước:** `calculate_change(USER_ID, 'decade')` hoặc `''`.
- **Kết quả mong đợi:** Raise `ValueError('unsupported period')` hoặc tương đương rõ ràng. KHÔNG silent fallback về `'day'`.

### TC-1.4.C8 — Net worth giảm → change âm + emoji 📉 (consumer hint)
- **Bước:** Hôm qua 100tr, hôm nay 80tr. `calculate_change(USER_ID, 'day')`.
- **Kết quả mong đợi:** `change_absolute == -20000000`, `change_percentage == Decimal('-20.00')`. Sign giữ đúng (Decimal có dấu).

### TC-1.4.C9 — `calculate_change()` khi `previous == 0` → KHÔNG ZeroDivisionError
- **Bước:** User mới, asset đầu tiên hôm nay 100tr. Gọi `calculate_change(USER_ID, 'day')`.
- **Kết quả mong đợi:**
  - `previous == 0`, `current == 100000000`, `change_absolute == 100000000`.
  - `change_percentage` xử lý phép chia 0: hoặc trả `0`, hoặc `Decimal('Infinity')` được handle, hoặc `None`. **Document rõ contract** — KHÔNG raise ZeroDivisionError.

### TC-1.4.C10 — DISTINCT ON performance trên dataset lớn
- **Mục tiêu:** Verify query historical KHÔNG là N+1.
- **Bước:**
  1. Setup user với 50 assets, mỗi asset 100 snapshots (=5000 rows).
  2. Bật log SQL.
  3. Gọi `calculate_historical(USER_ID, some_date)`.
- **Kết quả mong đợi:**
  - **Đúng 1 query** dùng `DISTINCT ON (asset_id) ... ORDER BY asset_id, snapshot_date DESC` (hoặc tương đương 1 query window function).
  - KHÔNG có 50 query lẻ tẻ.
  - Wall-clock < 200ms.

### TC-1.4.C11 — Cross-user isolation: user B không thấy asset của user A
- **Bước:** User A có 5 asset 200tr. User B 0 asset. `calculate(USER_B_ID)`.
- **Kết quả mong đợi:** `total == 0`. **Critical security test** — query phải có `WHERE user_id = :user_id`.

### TC-1.4.C12 — `largest_asset` khi nhiều asset cùng giá trị max
- **Bước:** 2 asset đều 100tr (tied for largest).
- **Kết quả mong đợi:** Trả về 1 trong 2 (deterministic theo `created_at` ASC hoặc id) — document rule rõ. KHÔNG random mỗi call.

### TC-1.4.C13 — `calculate_change()` với asset bị soft-delete giữa kỳ
- **Bước:**
  1. Hôm qua: 2 asset (50tr + 50tr = 100tr). Snapshot 2 cái.
  2. Hôm nay: soft-delete 1 asset. `current` chỉ còn 50tr.
  3. Gọi `calculate_change(USER_ID, 'day')`.
- **Kết quả mong đợi:**
  - `previous == 100000000` (lúc đó cả 2 active).
  - `current == 50000000` (chỉ còn 1 active).
  - `change_absolute == -50000000`. **Document:** `calculate_historical()` chỉ filter snapshot, KHÔNG filter is_active của asset hiện tại — có thể dẫn đến confusion. Cần spec rõ semantics.

### TC-1.4.C14 — Multiple snapshots cùng asset cùng ngày → lấy 1 (theo UNIQUE)
- **Bước:** UNIQUE constraint từ migration đảm bảo chỉ 1 snapshot/ngày/asset. Verify query historical không double-count.
- **Kết quả mong đợi:** Total của 1 asset trong 1 ngày = đúng 1 lần value của nó.

### TC-1.4.C15 — Round/precision của `change_percentage`
- **Bước:** previous=300tr, current=333,333,333. Tính %.
- **Kết quả mong đợi:** Trả về `Decimal` với precision rõ ràng (vd 2 chữ số: `11.11`). KHÔNG float lệch (`11.111111111111`). Document số chữ số thập phân.

---

# P3A-5 — Wealth Level Detection (Ladder)

**Maps to AC:** `WealthLevel` enum, `detect_level()` đúng 4 bracket, `next_milestone()` đúng target + level, boundary values (29tr, 30tr, 200tr, 1tỷ), update `user.wealth_level` khi asset thay đổi.

## Happy Path

### TC-1.5.H1 — `WealthLevel` enum đầy đủ 4 values
- **Bước:** `python -c "from app.wealth.ladder import WealthLevel; print([e.value for e in WealthLevel])"`
- **Kết quả mong đợi:** Output đúng 4: `['starter', 'young_prof', 'mass_affluent', 'hnw']`.

### TC-1.5.H2 — `detect_level()` cho 4 mid-range values
- **Bước:**
  ```python
  detect_level(Decimal('10_000_000'))      # → STARTER
  detect_level(Decimal('100_000_000'))     # → YOUNG_PROFESSIONAL
  detect_level(Decimal('500_000_000'))     # → MASS_AFFLUENT
  detect_level(Decimal('5_000_000_000'))   # → HIGH_NET_WORTH
  ```
- **Kết quả mong đợi:** Trả về đúng enum tương ứng.

### TC-1.5.H3 — `detect_level(Decimal('0'))` → STARTER
- **Bước:** `detect_level(Decimal('0'))`.
- **Kết quả mong đợi:** `WealthLevel.STARTER`. User mới 0 đồng vẫn ở Starter.

### TC-1.5.H4 — `next_milestone()` cho user starter
- **Bước:** `next_milestone(Decimal('15_000_000'))`.
- **Kết quả mong đợi:** Trả về `(Decimal('30_000_000'), WealthLevel.YOUNG_PROFESSIONAL)`.

### TC-1.5.H5 — `next_milestone()` step trong YOUNG_PROFESSIONAL bracket
- **Bước:** Theo spec line 656-665 có sub-milestones:
  - `next_milestone(Decimal('50_000_000'))` → `(100_000_000, YOUNG_PROFESSIONAL)`.
  - `next_milestone(Decimal('150_000_000'))` → `(200_000_000, MASS_AFFLUENT)`.
- **Kết quả mong đợi:** Đúng từng step.

### TC-1.5.H6 — `next_milestone()` step trong MASS_AFFLUENT bracket
- **Bước:**
  - `next_milestone(Decimal('300_000_000'))` → `(500_000_000, MASS_AFFLUENT)`.
  - `next_milestone(Decimal('700_000_000'))` → `(1_000_000_000, HIGH_NET_WORTH)`.

### TC-1.5.H7 — Update `user.wealth_level` khi asset thay đổi
- **Bước:**
  1. User có 25tr (starter). Verify `user.wealth_level == 'starter'`.
  2. Tạo thêm asset 10tr (tổng 35tr).
  3. Reload user từ DB.
- **Kết quả mong đợi:** `user.wealth_level == 'young_prof'` (auto-recompute trong `create_asset` hoặc trigger sau create).

## Corner Cases

### TC-1.5.C1 — Boundary 30tr — exclusive vs inclusive
- **Bước:**
  ```python
  detect_level(Decimal('29_999_999'))   # → STARTER (still <30tr)
  detect_level(Decimal('30_000_000'))   # → YOUNG_PROFESSIONAL (theo spec line 644-645: < 30tr STARTER)
  ```
- **Kết quả mong đợi:** Đúng 30tr là **YOUNG_PROFESSIONAL** (vì điều kiện `< 30_000_000`). **Quan trọng** — verify off-by-one không xảy ra.

### TC-1.5.C2 — Boundary 200tr
- **Bước:**
  - `detect_level(Decimal('199_999_999'))` → YOUNG_PROFESSIONAL.
  - `detect_level(Decimal('200_000_000'))` → MASS_AFFLUENT.
- **Kết quả mong đợi:** Đúng theo spec `< 200_000_000`.

### TC-1.5.C3 — Boundary 1 tỷ
- **Bước:**
  - `detect_level(Decimal('999_999_999'))` → MASS_AFFLUENT.
  - `detect_level(Decimal('1_000_000_000'))` → HIGH_NET_WORTH.
- **Kết quả mong đợi:** Đúng.

### TC-1.5.C4 — `next_milestone()` cho HNW (logic theo tỷ)
- **Bước:**
  - `next_milestone(Decimal('1_000_000_000'))` → `(2_000_000_000, HNW)` (tỷ tiếp theo).
  - `next_milestone(Decimal('2_500_000_000'))` → `(3_000_000_000, HNW)`.
  - `next_milestone(Decimal('15_700_000_000'))` → `(16_000_000_000, HNW)`.
- **Kết quả mong đợi:** Tăng dần theo `floor(net_worth / 1tỷ) + 1`.

### TC-1.5.C5 — `detect_level()` với giá trị âm (data corruption)
- **Bước:** `detect_level(Decimal('-1000'))`.
- **Kết quả mong đợi:** Trả về `STARTER` (an toàn) hoặc raise `ValueError`. Document chọn behavior nào — KHÔNG crash silently.

### TC-1.5.C6 — `detect_level(Decimal('0.01'))` (precision tí)
- **Bước:** Net worth = 1 cent.
- **Kết quả mong đợi:** STARTER. Decimal arithmetic ổn định (không bị float lệch).

### TC-1.5.C7 — `next_milestone()` cho user vừa đạt boundary
- **Bước:** Net worth = đúng 30tr.
- **Kết quả mong đợi:** Theo spec line 658: `< 100_000_000` → trả về `(100_000_000, YOUNG_PROFESSIONAL)`. Verify user vừa lên YP được prompt mục tiêu 100tr (chứ không loop về 30tr).

### TC-1.5.C8 — `wealth_level` recompute KHÔNG bị stale khi user soft-delete asset
- **Bước:**
  1. User 35tr (young_prof). Soft-delete asset 10tr → còn 25tr.
  2. Reload user.
- **Kết quả mong đợi:** `user.wealth_level == 'starter'` (giảm cấp). Verify cả 2 chiều: lên cấp + xuống cấp đều update.

### TC-1.5.C9 — `wealth_level` recompute trigger ở update_current_value()
- **Bước:** User có 1 asset 25tr. Update giá trị lên 35tr (qua `update_current_value`).
- **Kết quả mong đợi:** `user.wealth_level` chuyển `starter` → `young_prof`. KHÔNG chỉ trigger ở create.

### TC-1.5.C10 — Boundary với Decimal precision khó (29.99999999tr)
- **Bước:** `detect_level(Decimal('29999999.99'))`.
- **Kết quả mong đợi:** STARTER (vẫn `< 30_000_000`).

### TC-1.5.C11 — `next_milestone()` trả về (Decimal, WealthLevel)
- **Bước:** Inspect type của return.
- **Kết quả mong đợi:** Tuple `(Decimal, WealthLevel)`. Money là Decimal, KHÔNG int hay float.

### TC-1.5.C12 — Cross-user wealth_level không ảnh hưởng nhau
- **Bước:** User A 35tr (YP). User B 5tr (Starter). Update A lên 250tr (Mass Affluent).
- **Kết quả mong đợi:** B vẫn Starter, KHÔNG bị side-effect.

### TC-1.5.C13 — `wealth_level` không bị flicker khi value sát boundary
- **Bước:** User 30,000,000 đúng (YP). Update value xuống 29,999,999 → lên lại 30,000,001.
- **Kết quả mong đợi:** Mỗi lần level chuyển đúng (YP → Starter → YP). Không có race / cache stale.

---

# P3A-6 — Asset Entry Wizard: Cash Flow

**Maps to AC:** `start_cash_wizard()`, `handle_cash_subtype()`, `handle_cash_text_input()` parse flexible, save với `source="user_input"`, confirmation + net worth update, "Thêm tài sản khác" button, validation âm/zero, error parse → ask graceful.

> **Setup:** Test qua Telegram bot trên test account, hoặc unit test handler với mock Update/Context.

## Happy Path

### TC-1.6.H1 — `/start` → `start_cash_wizard()` show 4 subtype buttons
- **Bước:** Trong onboarding hoặc gọi command `/them_tai_san` → chọn "Tiền mặt / TK".
- **Kết quả mong đợi:**
  - Bot hiển thị message "💵 Tiền ở đâu?" (theo spec line 749).
  - 4 inline buttons: "🏦 Tiết kiệm ngân hàng", "💳 Tài khoản thanh toán", "💵 Tiền mặt", "📱 Ví điện tử".
  - Callback data: `cash_subtype:bank_savings|bank_checking|cash|e_wallet`.

### TC-1.6.H2 — Tap "Tiết kiệm ngân hàng" → ask tên + số tiền
- **Bước:** Tap button "🏦 Tiết kiệm ngân hàng".
- **Kết quả mong đợi:**
  - Bot reply "💬 Tên ngân hàng + số tiền\n\nVí dụ: 'VCB 100 triệu' hoặc 'Techcom 50tr'".
  - `context.user_data["asset_draft"] == {"asset_type": "cash", "subtype": "bank_savings"}`.
  - `context.user_data["asset_draft_step"] == "cash_amount"`.

### TC-1.6.H3 — Parse "VCB 100 triệu" → save asset đúng
- **Bước:** Sau khi chọn bank_savings, gửi message "VCB 100 triệu".
- **Kết quả mong đợi:**
  - Asset được tạo: `name='VCB'`, `asset_type='cash'`, `subtype='bank_savings'`, `initial_value=Decimal('100000000')`, `current_value=Decimal('100000000')`.
  - `source = 'user_input'` (verify qua DB hoặc API).
  - Bot reply confirmation message + net worth update mới.

### TC-1.6.H4 — Parse "Techcom 50tr" (variant ngắn)
- **Bước:** Gửi "Techcom 50tr".
- **Kết quả mong đợi:** `name='Techcom'`, `initial_value=Decimal('50000000')`.

### TC-1.6.H5 — Parse "MoMo 2tr" (e-wallet)
- **Bước:** Subtype `e_wallet`, gửi "MoMo 2tr".
- **Kết quả mong đợi:** `name='MoMo'`, `initial_value=Decimal('2000000')`, `subtype='e_wallet'`.

### TC-1.6.H6 — Parse "Tiết kiệm 500 nghìn"
- **Bước:** Gửi "Tiết kiệm 500 nghìn".
- **Kết quả mong đợi:** `name='Tiết kiệm'`, `initial_value=Decimal('500000')`.

### TC-1.6.H7 — Sau save: hiển thị confirm + net worth + offer "Thêm tài sản khác"
- **Bước:** Sau khi parse + save thành công.
- **Kết quả mong đợi:**
  - Confirmation message có icon ✅, tên asset, value formatted (vd "100tr").
  - Net worth mới hiển thị (gọi `NetWorthCalculator`).
  - Inline keyboard 2 buttons: "➕ Thêm tài sản khác" (callback `asset_add:start`) + "✅ Xong rồi" (callback `asset_add:done`).

### TC-1.6.H8 — `context.user_data["asset_draft"]` clear sau save
- **Bước:** Inspect `context.user_data` sau khi save xong.
- **Kết quả mong đợi:** Cả `asset_draft` và `asset_draft_step` bị `pop()` — KHÔNG leak vào flow tiếp theo.

### TC-1.6.H9 — "Tiền mặt" subtype không cần tên ngân hàng
- **Bước:** Tap "💵 Tiền mặt" → gửi "5 triệu".
- **Kết quả mong đợi:** Asset name fallback = "Tài khoản" (theo spec line 858) hoặc "Tiền mặt". `initial_value = 5000000`.

## Corner Cases

### TC-1.6.C1 — Parse số âm "VCB -100tr" → reject
- **Bước:** Gửi "VCB -100 triệu".
- **Kết quả mong đợi:** Bot reply "Số tiền phải lớn hơn 0 nhé" (hoặc tương đương ấm áp). KHÔNG tạo asset. State giữ nguyên `cash_amount` để user retry.

### TC-1.6.C2 — Parse số 0 "VCB 0" → reject
- **Bước:** "VCB 0".
- **Kết quả mong đợi:** Reject với message rõ. Asset KHÔNG được tạo.

### TC-1.6.C3 — Parse fail "abc xyz qwe" → ask graceful
- **Bước:** Gửi text vô nghĩa.
- **Kết quả mong đợi:** Bot reply theo spec line 802-805: "Mình chưa hiểu lắm 😅 Bạn thử lại theo format 'Tên + số tiền' nhé?\nVí dụ: 'VCB 100 triệu'". State KHÔNG reset, user có thể retry mà không phải tap lại subtype.

### TC-1.6.C4 — Parse chỉ có số "100tr" (thiếu tên)
- **Bước:** Gửi "100tr" (không có tên).
- **Kết quả mong đợi:** Asset được tạo với name fallback (vd "Tài khoản" theo spec line 858). KHÔNG raise.

### TC-1.6.C5 — Parse chỉ có tên "VCB" (thiếu số)
- **Bước:** Gửi "VCB" (không có amount).
- **Kết quả mong đợi:** Reject — `parse_cash_input` trả None → bot ask retry.

### TC-1.6.C6 — Số rất lớn "VCB 100 tỷ"
- **Bước:** "VCB 100 tỷ".
- **Kết quả mong đợi:** `initial_value = Decimal('100000000000')`. Lưu được, hiển thị format "100 tỷ" hoặc "100,000tr".

### TC-1.6.C7 — Số có dấu phẩy/chấm "VCB 1,500,000"
- **Bước:** "VCB 1,500,000".
- **Kết quả mong đợi:** Parse đúng `1_500_000`. Test thêm: "1.500.000" (kiểu VN), "1500000" (raw).

### TC-1.6.C8 — Text input không trong wizard mode → handler trả False
- **Bước:** User KHÔNG ở step `cash_amount` (vd vừa start, chưa chọn subtype). Gửi text.
- **Kết quả mong đợi:** `handle_cash_text_input` return `False` (theo spec line 793-794) — message được route cho handler khác. KHÔNG crash, KHÔNG tạo asset nhầm.

### TC-1.6.C9 — User tap subtype 2 lần (race / double click)
- **Bước:** Tap "bank_savings" → tap "e_wallet" trước khi gửi text.
- **Kết quả mong đợi:** Subtype cuối cùng (`e_wallet`) được lưu vào draft. Bot show prompt mới cho e_wallet, ghi đè prompt cũ.

### TC-1.6.C10 — User abandon flow giữa chừng (timeout / quên)
- **Bước:** Tap subtype, đợi 1 giờ, gửi text.
- **Kết quả mong đợi:** Hoặc:
  - State vẫn còn (Telegram persistent context) → save normal.
  - Hoặc state đã expire → bot ask "Bạn đang định thêm gì nhỉ?". Document timeout policy.

### TC-1.6.C11 — Send sticker / photo trong cash_amount step
- **Bước:** Đang ở step `cash_amount`, gửi sticker thay vì text.
- **Kết quả mong đợi:** Bot reply "Mình chỉ hiểu text thôi nhé, gửi lại theo format 'Tên + số tiền'". KHÔNG crash.

### TC-1.6.C12 — Tên có dấu tiếng Việt "Vietcombank"
- **Bước:** "Vietcombank 100tr".
- **Kết quả mong đợi:** `name='Vietcombank'`. UTF-8 round-trip qua DB không lỗi.

### TC-1.6.C13 — Tên dài bất thường (>200 chars)
- **Bước:** Gửi name 500 ký tự + số.
- **Kết quả mong đợi:** Hoặc truncate về 200 (theo `varchar(200)` của DB), hoặc reject với message "Tên ngân hàng quá dài". KHÔNG raise SQLAlchemy lỗi crash bot.

### TC-1.6.C14 — Số tiền cực nhỏ "VCB 1 đồng"
- **Bước:** Gửi "VCB 1".
- **Kết quả mong đợi:** Lưu `initial_value=Decimal('1')`. Edge case rare nhưng không crash.

### TC-1.6.C15 — Parse multiline "VCB\n100tr"
- **Bước:** Text có newline giữa name và amount.
- **Kết quả mong đợi:** Hoặc parse được (strip whitespace), hoặc reject với message rõ. Document.

### TC-1.6.C16 — Confirmation message format tiền đúng VN style
- **Bước:** Save asset 1,500,000.
- **Kết quả mong đợi:** Confirmation hiển thị "1.5tr" hoặc "1,500,000đ" theo `currency_utils.format_money_short` (CLAUDE.md §13). KHÔNG raw "1500000".

### TC-1.6.C17 — Tap "Thêm tài sản khác" → restart wizard sạch
- **Bước:** Sau save, tap "➕ Thêm tài sản khác".
- **Kết quả mong đợi:** Quay về `start_asset_entry_wizard()` với 6 buttons. Draft state đã clear. Asset cũ không bị duplicate.

### TC-1.6.C18 — Tap "Xong rồi" → exit về main menu
- **Bước:** Tap "✅ Xong rồi".
- **Kết quả mong đợi:** Bot show main menu hoặc summary. KHÔNG còn ở wizard mode.

### TC-1.6.C19 — Cross-user: User A's draft KHÔNG ảnh hưởng User B
- **Bước:** A đang ở giữa wizard, B cũng start wizard cùng lúc.
- **Kết quả mong đợi:** Mỗi user có context riêng (Telegram per-user). Asset của A được tạo cho user_id A, B cho B. Không leak.

### TC-1.6.C20 — Wizard cancel command "/cancel" hoặc "/huy"
- **Bước:** Đang giữa wizard, gửi `/cancel`.
- **Kết quả mong đợi:** Bot xác nhận hủy, clear draft, về main menu. (Nếu spec không có cancel command, document và đề xuất add.)

---

# P3A-7 — Asset Entry Wizard: Stock Flow

**Maps to AC:** `start_stock_wizard()`, `handle_stock_ticker()`, `handle_stock_quantity()`, `handle_stock_price()`, `handle_stock_current_price()` (same/new), metadata `{ticker, quantity, avg_price, exchange}`, support subtypes `vn_stock|fund|etf|foreign_stock`, ticker không tồn tại vẫn lưu (Phase 3B validate), normalize "VNM stocks" → "VNM", `initial_value = quantity * avg_price`, `current_value = quantity * current_price`.

> **Setup:** Như P3A-6 (Telegram test account hoặc unit test với mock Update/Context). Đã chọn loại "📈 Chứng khoán" từ wizard chính (callback `asset_add:stock`).

## Happy Path

### TC-1.7.H1 — `start_stock_wizard()` show prompt nhập ticker
- **Mục tiêu:** Verify entry point của stock flow đúng spec.
- **Bước:** Trigger callback `asset_add:stock` (hoặc gọi trực tiếp `start_stock_wizard()`).
- **Kết quả mong đợi:**
  - Bot reply text "📈 Cổ phiếu / Quỹ mới\n\nMã cổ phiếu (ticker) là gì?\n\nVí dụ: VNM, VIC, HPG, E1VFVN30" (theo spec line 874-878).
  - `context.user_data["asset_draft"] == {"asset_type": "stock"}`.
  - `context.user_data["asset_draft_step"] == "stock_ticker"`.

### TC-1.7.H2 — `handle_stock_ticker()` lưu ticker upper-case + chuyển step
- **Bước:** Đang ở step `stock_ticker`, gửi text "VNM".
- **Kết quả mong đợi:**
  - `context.user_data["asset_draft"]["metadata"] == {"ticker": "VNM"}`.
  - `context.user_data["asset_draft_step"] == "stock_quantity"`.
  - Bot reply "✅ VNM\n\nBạn đang sở hữu bao nhiêu cổ phiếu?" (spec line 891-894).

### TC-1.7.H3 — Ticker lower-case "vnm" → normalize uppercase "VNM"
- **Bước:** Gửi "vnm" (lower).
- **Kết quả mong đợi:** Metadata lưu `ticker == 'VNM'` (theo spec dùng `.strip().upper()` line 887).

### TC-1.7.H4 — Ticker có whitespace "  HPG  " → strip
- **Bước:** Gửi "  HPG  ".
- **Kết quả mong đợi:** `ticker == 'HPG'`. Không có space leak vào DB.

### TC-1.7.H5 — `handle_stock_quantity()` parse integer thuần
- **Bước:** Đang ở step `stock_quantity`, gửi "100".
- **Kết quả mong đợi:**
  - `metadata["quantity"] == 100` (int, không Decimal cho quantity).
  - `asset_draft_step == 'stock_price'`.
  - Bot reply "✅ 100 cổ phiếu\n\nGiá mua trung bình mỗi cổ phiếu?\n(Ví dụ: '45000' hoặc '45k')".

### TC-1.7.H6 — Parse quantity với dấu phẩy "1,000"
- **Bước:** Gửi "1,000".
- **Kết quả mong đợi:** `quantity == 1000` (theo spec line 903 `replace(",", "").replace(".", "")`).

### TC-1.7.H7 — Parse quantity dạng VN "1.000" (dấu chấm phân cách nghìn)
- **Bước:** Gửi "1.000".
- **Kết quả mong đợi:** `quantity == 1000`.

### TC-1.7.H8 — `handle_stock_price()` parse "45000" → lưu avg_price + tính total_value
- **Bước:** Step `stock_price`, gửi "45000".
- **Kết quả mong đợi:**
  - `metadata["avg_price"] == 45000` (Decimal hoặc number).
  - Bot tính `total_value = 100 * 45000 = 4_500_000` và hiển thị (spec line 947-948).
  - Reply có 2 inline buttons: "Dùng 45,000đ (giá mua)" (callback `stock_price:same`) và "Nhập giá hiện tại" (callback `stock_price:new`).

### TC-1.7.H9 — Parse avg_price dạng "45k" qua `parse_transaction_text`
- **Bước:** Gửi "45k".
- **Kết quả mong đợi:** `avg_price == 45000`. Reuse `parse_transaction_text` từ Phase 3 (CLAUDE.md spec).

### TC-1.7.H10 — Tap "Dùng giá mua" (callback `stock_price:same`) → save asset, current_price = avg_price
- **Bước:** Sau khi nhập price, tap button "Dùng 45,000đ (giá mua)".
- **Kết quả mong đợi:**
  - Asset được tạo với `metadata = {"ticker": "VNM", "quantity": 100, "avg_price": 45000}`.
  - `initial_value == Decimal('4500000')` (= quantity × avg_price).
  - `current_value == Decimal('4500000')` (cùng giá mua).
  - Bot show confirmation + net worth update + offer "Thêm tài sản khác".

### TC-1.7.H11 — Tap "Nhập giá hiện tại" → ask current_price → save với value khác
- **Bước:**
  1. Tap "Nhập giá hiện tại" (callback `stock_price:new`).
  2. Bot ask "Giá hiện tại của cổ phiếu?".
  3. Gửi "50000".
- **Kết quả mong đợi:**
  - `metadata["current_price"]` lưu hoặc dùng để tính `current_value`.
  - `initial_value == Decimal('4500000')` (theo avg_price).
  - `current_value == Decimal('5000000')` (= 100 × 50000).
  - Asset save thành công, source = `'user_input'`.

### TC-1.7.H12 — Subtype mặc định cho stock = `vn_stock` (HOSE)
- **Bước:** Không chọn subtype rõ ràng (wizard mặc định).
- **Kết quả mong đợi:** `asset.subtype == 'vn_stock'` và `metadata["exchange"] == 'HOSE'` (theo spec § 1.6 line 289 và CLAUDE.md asset_categories).

### TC-1.7.H13 — Wizard support 4 subtypes: vn_stock, fund, etf, foreign_stock
- **Mục tiêu:** Verify wizard có thể nhánh sang fund/ETF/foreign nếu user chọn.
- **Bước:** Trigger các callback subtype tương ứng (qua menu sub-selection nếu spec có, hoặc field metadata `subtype` được set).
- **Kết quả mong đợi:** 4 path đều dẫn đến save thành công với `asset.subtype` đúng. ETF có thể không cần ticker validate (E1VFVN30 ok).

### TC-1.7.H14 — Sau save: confirmation message hiển thị format VN
- **Bước:** Save asset 100 VNM × 45,000.
- **Kết quả mong đợi:** Confirmation hiển thị "VNM × 100 cp · 4.5tr" (hoặc tương đương qua `currency_utils.format_money_short`). KHÔNG raw "4500000".

### TC-1.7.H15 — Draft state clear sau save
- **Bước:** Inspect `context.user_data` sau khi save xong.
- **Kết quả mong đợi:** Cả `asset_draft` và `asset_draft_step` bị `pop()`. Không leak vào flow tiếp.

## Corner Cases

### TC-1.7.C1 — Ticker không tồn tại "ZZZ999" → vẫn cho save (Phase 3B validate)
- **Bước:** Gửi "ZZZ999" làm ticker.
- **Kết quả mong đợi:** Asset save bình thường với `ticker='ZZZ999'`. Phase 3A KHÔNG validate ticker thật. Document: Phase 3B sẽ check vnstock và warn.

### TC-1.7.C2 — Normalize "VNM stocks" → "VNM"
- **Bước:** Gửi "VNM stocks" (user thêm chữ rác).
- **Kết quả mong đợi:** `metadata["ticker"] == 'VNM'` (strip word "stocks"). Spec acceptance criteria P3A-7 line 293 yêu cầu rõ.
- **Note:** Nếu spec chỉ làm `.upper().strip()` (line 887), test này có thể FAIL — cần thêm regex/whitelist ký tự alpha. Document gap.

### TC-1.7.C3 — Ticker chứa số "E1VFVN30" (ETF)
- **Bước:** Gửi "E1VFVN30".
- **Kết quả mong đợi:** Lưu nguyên "E1VFVN30". Verify regex normalize không cắt mất số.

### TC-1.7.C4 — Ticker quá dài hoặc ký tự lạ "!@#$"
- **Bước:** Gửi "!@#$" hoặc "VNMVNMVNMVNMVNM" (15+ chars).
- **Kết quả mong đợi:** Hoặc reject với message "Mã cổ phiếu không hợp lệ", hoặc cho lưu (Phase 3B validate). Document chọn behavior.

### TC-1.7.C5 — Quantity không phải số "abc"
- **Bước:** Step `stock_quantity`, gửi "abc".
- **Kết quả mong đợi:** Bot reply "Nhập số thôi nhé, ví dụ: 100" (theo spec line 905). State KHÔNG reset, vẫn ở `stock_quantity`. User retry được.

### TC-1.7.C6 — Quantity âm "-100"
- **Bước:** Gửi "-100".
- **Kết quả mong đợi:** Reject với message rõ "Số cổ phiếu phải > 0". KHÔNG lưu negative quantity.
- **Note:** `int("-100")` parse được → service phải validate tiếp, không chỉ dựa try/except.

### TC-1.7.C7 — Quantity = 0
- **Bước:** Gửi "0".
- **Kết quả mong đợi:** Reject (không có lý do hold 0 cp). Hoặc lưu nhưng cảnh báo. Document.

### TC-1.7.C8 — Quantity float "100.5" (mua phần lẻ ETF)
- **Bước:** Gửi "100.5".
- **Kết quả mong đợi:**
  - Theo spec line 903 strip cả "." → parse thành `1005` (sai!).
  - Hoặc spec yêu cầu integer → reject với message.
  - **Document:** Việt Nam thường giao dịch nguyên cổ; nếu support fractional cho fund thì cần parse khác. Note gap nếu có.

### TC-1.7.C9 — Quantity rất lớn (1 triệu cp)
- **Bước:** Gửi "1000000".
- **Kết quả mong đợi:** Lưu được. `total_value = 1_000_000 × 45_000 = 45 tỷ`. Format hiển thị "45 tỷ" hoặc "45,000tr".

### TC-1.7.C10 — Avg price parse fail ("xyz")
- **Bước:** Step `stock_price`, gửi "xyz".
- **Kết quả mong đợi:** Bot reply "Nhập giá giúp mình nhé, ví dụ '45k' hoặc '45000'" (theo spec line 930). State giữ `stock_price`.

### TC-1.7.C11 — Avg price = 0 hoặc âm
- **Bước:** Gửi "0" hoặc "-1000".
- **Kết quả mong đợi:** Reject với message "Giá phải > 0". KHÔNG lưu asset với `initial_value = 0`. Service layer validate (P3A-3 TC-1.3.C9).

### TC-1.7.C12 — Avg price decimal nhỏ "0.5" (penny stock)
- **Bước:** Gửi "0.5".
- **Kết quả mong đợi:** Lưu `avg_price = Decimal('0.5')`. Edge case rare nhưng không crash. Total value = 50 (cho 100 cp).

### TC-1.7.C13 — Current price < avg price (lỗ)
- **Bước:** Avg = 50000, current = 30000.
- **Kết quả mong đợi:**
  - `initial_value = 5_000_000`, `current_value = 3_000_000`.
  - `gain_loss = -2_000_000` (Decimal âm, hybrid property TC-1.2.H6).
  - Confirmation hiển thị "📉 -2tr" hoặc tương đương.

### TC-1.7.C14 — Current price > avg price rất nhiều (10x)
- **Bước:** Avg = 10000, current = 100000.
- **Kết quả mong đợi:** `gain_loss = +9_000_000`. Confirmation hiển thị "📈 +9tr" hoặc tương đương.

### TC-1.7.C15 — Tap "stock_price:same" 2 lần liên tiếp (double tap)
- **Bước:** Tap nhanh 2 lần button "Dùng giá mua".
- **Kết quả mong đợi:** Chỉ tạo **1** asset (dedup qua draft state đã clear sau lần 1, hoặc qua callback handler idempotent). KHÔNG tạo duplicate.

### TC-1.7.C16 — Text input ngoài stock_* steps → handler trả False
- **Bước:** User chưa enter wizard, gửi text "100" hoặc "VNM".
- **Kết quả mong đợi:** `handle_stock_ticker/quantity/price` đều return `False` (theo spec line 884-885, 899-900, 920-921). Message route handler khác. KHÔNG nhầm lẫn create asset rỗng.

### TC-1.7.C17 — Abandon flow giữa chừng (stop ở stock_quantity)
- **Bước:** Nhập ticker xong, không nhập quantity. Đóng app.
- **Kết quả mong đợi:** State giữ trong `context.user_data` (Telegram persistent) → quay lại có thể tiếp tục. Hoặc timeout policy xóa. Document. KHÔNG có asset rỗng (`initial_value=null`) bị flush vào DB.

### TC-1.7.C18 — User gửi sticker / photo trong stock_ticker step
- **Bước:** Step `stock_ticker`, gửi photo.
- **Kết quả mong đợi:** Bot reply "Mình cần text mã cổ phiếu thôi, ví dụ 'VNM'". KHÔNG crash.

### TC-1.7.C19 — Cross-user: User A's asset_draft KHÔNG ảnh hưởng B
- **Bước:** A đang ở step `stock_price`. B start stock wizard cùng lúc.
- **Kết quả mong đợi:** `context.user_data` per-user (Telegram framework guarantee). Asset của A → user_id A, B → B. Không leak ticker / quantity giữa 2 users.

### TC-1.7.C20 — Asset save nhưng `wealth_level` recompute (P3A-5 dependency)
- **Bước:** User starter (5tr cash). Save VNM 100 × 300,000 = 30tr stock.
- **Kết quả mong đợi:**
  - Total net worth = 35tr → `user.wealth_level` chuyển `starter` → `young_prof`.
  - Verify `create_asset` trigger ladder recompute (TC-1.5.H7 chéo).

### TC-1.7.C21 — Confirmation message format số nguyên không thừa decimal
- **Bước:** Save 100 cp × 45,000.
- **Kết quả mong đợi:** Hiển thị "4.5tr" hoặc "4,500,000đ", KHÔNG "4500000.00". `format_money_short` strip trailing zeros khi nguyên.

### TC-1.7.C22 — Cancel command "/cancel" giữa wizard
- **Bước:** Đang ở `stock_quantity`, gửi `/cancel` (nếu spec có).
- **Kết quả mong đợi:** Clear draft, bot xác nhận hủy, về main menu. Nếu spec không có → document gap (như P3A-6 TC-1.6.C20).

### TC-1.7.C23 — Foreign stock (subtype `foreign_stock`) với ticker dài "AAPL"
- **Bước:** Subtype `foreign_stock`, ticker "AAPL", quantity 10, avg_price 150 USD (note: VND-only theo CLAUDE.md `currency='VND'`).
- **Kết quả mong đợi:**
  - Hoặc lưu raw value VND quy đổi (user tự quy đổi).
  - Hoặc reject với message "Phase 3A chỉ support cổ phiếu VN" — document spec.

### TC-1.7.C24 — Decimal precision trong tính `initial_value`
- **Bước:** quantity = 333, avg_price = 12345.
- **Kết quả mong đợi:** `initial_value = Decimal('4110885')` exact. KHÔNG `4110884.99...` do float drift. Verify Decimal arithmetic xuyên suốt.

### TC-1.7.C25 — Snapshot đầu tiên match `current_value`, không match `initial_value`
- **Bước:** Save với avg=45k, current=50k. Verify snapshot.
- **Kết quả mong đợi:** First snapshot có `value = current_value = 5_000_000` (theo P3A-3 TC-1.3.H1 logic), KHÔNG `initial_value`. NetWorthCalculator sẽ dùng `current_value`.

---

> **DỪNG TẠI ĐÂY** — Các issue P3A-8, P3A-9 sẽ được bổ sung trong các lần ghi tiếp theo.
