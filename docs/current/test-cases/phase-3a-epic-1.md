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

> **DỪNG TẠI ĐÂY** — Các issue P3A-3 đến P3A-9 sẽ được bổ sung trong các lần ghi tiếp theo.
