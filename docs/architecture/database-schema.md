## Database Schema (PostgreSQL)

### Nguyên tắc schema
- **Mọi table đều có `user_id` (UUID, NOT NULL, indexed)**
- Dùng UUID cho primary keys — tránh conflict khi merge data
- `created_at` và `updated_at` trên mọi table
- Soft delete với `deleted_at` hoặc `is_active` — không xóa cứng data
- Money fields dùng `NUMERIC(20, 2)` (không dùng Float!)

### Table: `users` (UPDATED cho V2)
```sql
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_id     BIGINT UNIQUE NOT NULL,
    telegram_handle VARCHAR(255),
    display_name    VARCHAR(255),
    timezone        VARCHAR(50) DEFAULT 'Asia/Ho_Chi_Minh',
    currency        VARCHAR(10) DEFAULT 'VND',
    
    -- V1 legacy
    monthly_income  NUMERIC(15,2),
    
    -- V2 — Wealth management fields
    wealth_level    VARCHAR(20),               -- 'starter' | 'young_prof' | 'mass_affluent' | 'hnw'
    primary_goal    VARCHAR(30),               -- Từ Phase 2 onboarding
    onboarding_step INTEGER DEFAULT 0,
    onboarding_completed_at TIMESTAMPTZ,
    
    -- V2 — Threshold-based expense (adapt theo income)
    expense_threshold_micro  INTEGER DEFAULT 200000,  -- <= này gộp aggregate
    expense_threshold_major  INTEGER DEFAULT 2000000, -- >= này là major event
    
    -- V2 — Morning briefing
    briefing_enabled BOOLEAN DEFAULT true,
    briefing_time   TIME DEFAULT '07:00:00',
    
    is_active       BOOLEAN DEFAULT true,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ
);

CREATE INDEX idx_users_wealth_level ON users(wealth_level);
```

### Table: `assets` ⭐ NEW — Core của V2
```sql
CREATE TABLE assets (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id),
    
    -- Classification
    asset_type          VARCHAR(30) NOT NULL,
    -- Types: 'cash' | 'stock' | 'real_estate' | 'crypto' | 'gold' | 'other'
    subtype             VARCHAR(50),
    -- Examples:
    --   cash: 'bank_savings' | 'bank_checking' | 'cash' | 'e_wallet'
    --   stock: 'vn_stock' | 'fund' | 'etf' | 'foreign_stock'
    --   real_estate: 'house_primary' | 'land'  (rental trong Phase 4)
    --   crypto: 'bitcoin' | 'ethereum' | 'stablecoin' | 'altcoin'
    --   gold: 'sjc' | 'pnj' | 'nhan' | 'trang_suc'
    
    -- Identity
    name                VARCHAR(200) NOT NULL,
    description         TEXT,
    
    -- Value tracking
    initial_value       NUMERIC(20,2) NOT NULL,  -- Giá mua/gốc
    current_value       NUMERIC(20,2) NOT NULL,  -- Giá hiện tại
    acquired_at         DATE NOT NULL,
    last_valued_at      TIMESTAMPTZ DEFAULT NOW(),
    
    -- Flexible metadata (schema phụ thuộc asset_type)
    metadata            JSONB,
    -- stock:       {"ticker": "VNM", "quantity": 100, "avg_price": 45000, "exchange": "HOSE"}
    -- real_estate: {"address": "...", "area_sqm": 80, "year_built": 2015}
    -- crypto:      {"symbol": "BTC", "quantity": 0.5, "wallet": "Binance"}
    -- gold:        {"weight_gram": 10, "type": "SJC", "purity": "9999"}
    
    -- Status (soft delete pattern)
    is_active           BOOLEAN DEFAULT true,
    sold_at             DATE,
    sold_value          NUMERIC(20,2),
    
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_assets_user_active ON assets(user_id, is_active);
CREATE INDEX idx_assets_type ON assets(asset_type);
```

### Table: `asset_snapshots` ⭐ NEW — Daily historical values
```sql
CREATE TABLE asset_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    asset_id        UUID NOT NULL REFERENCES assets(id),
    user_id         UUID NOT NULL REFERENCES users(id),
    snapshot_date   DATE NOT NULL,
    value           NUMERIC(20,2) NOT NULL,
    source          VARCHAR(20) NOT NULL,
    -- Sources: 'user_input' | 'market_api' | 'auto_daily' | 'interpolated'
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(asset_id, snapshot_date)
);

CREATE INDEX idx_snapshots_user_date ON asset_snapshots(user_id, snapshot_date DESC);
```

**Tại sao cần snapshots:**
- Vẽ chart "Net worth 30/90/365 ngày qua"
- Tính "Tăng X% tháng này vs tháng trước"  
- Historical record cho tax reports
- Nếu user sold asset → history vẫn còn

### Table: `income_streams` ⭐ NEW — Simple income tracking
```sql
CREATE TABLE income_streams (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id),
    
    source_type         VARCHAR(30) NOT NULL,
    -- Types: 'salary' | 'dividend' | 'interest' | 'rental' | 'other'
    -- Note: 'rental' chỉ setup trong Phase 4 (cần rental_income_log table)
    
    name                VARCHAR(200) NOT NULL,
    amount_monthly      NUMERIC(15,2) NOT NULL,  -- Trung bình/tháng
    is_active           BOOLEAN DEFAULT true,
    
    metadata            JSONB,
    -- salary:   {"company": "...", "frequency": "monthly"}
    -- dividend: {"asset_id": "uuid", "annual_yield": 0.06}
    
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_income_user_active ON income_streams(user_id, is_active);
```

### Table: `transactions` (UPDATED — renamed from `expenses`)
```sql
CREATE TABLE transactions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    amount          NUMERIC(15,2) NOT NULL,
    currency        VARCHAR(10) DEFAULT 'VND',
    merchant        VARCHAR(500),
    category        VARCHAR(100) NOT NULL,
    -- Categories: 'food' | 'transport' | 'housing' | 'shopping' | 'health'
    --             'education' | 'entertainment' | 'utility' | 'gift'
    --             'saving' | 'investment' | 'transfer' | 'other'
    
    -- V2: source tracking (không có gmail, thêm storytelling)
    source          VARCHAR(50) NOT NULL,
    -- Sources: 'manual' | 'storytelling' | 'ocr' | 'voice' | 'wrap_up'
    
    -- V2: new fields cho threshold-based
    confidence      NUMERIC(3,2) DEFAULT 1.0,     -- 0.0-1.0, source confidence
    raw_input       TEXT,                          -- Preserve original input
    verified_by_user BOOLEAN DEFAULT false,
    
    transaction_date DATE NOT NULL,
    month_key       VARCHAR(7) NOT NULL,           -- '2026-04'
    note            TEXT,
    raw_data        JSONB,                          -- Debug data
    needs_review    BOOLEAN DEFAULT false,
    
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ
);

CREATE INDEX idx_transactions_user ON transactions(user_id);
CREATE INDEX idx_transactions_month ON transactions(user_id, month_key);
CREATE INDEX idx_transactions_source ON transactions(user_id, source);
```

**Deprecated columns (V1 → V2):**
- ~~`gmail_message_id`~~ — không còn Gmail integration

### Table: `user_milestones` (from Phase 2)
```sql
CREATE TABLE user_milestones (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    milestone_type  VARCHAR(50) NOT NULL,
    achieved_at     TIMESTAMPTZ DEFAULT NOW(),
    celebrated_at   TIMESTAMPTZ,
    metadata        JSONB
);

CREATE INDEX idx_milestones_user_type ON user_milestones(user_id, milestone_type);
CREATE INDEX idx_milestones_uncelebrated ON user_milestones(user_id, celebrated_at) 
    WHERE celebrated_at IS NULL;
```

### Table: `user_events` (from Phase 2)
```sql
CREATE TABLE user_events (
    id              BIGSERIAL PRIMARY KEY,
    user_id         UUID NOT NULL REFERENCES users(id),
    event_type      VARCHAR(50) NOT NULL,
    metadata        JSONB,
    timestamp       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_events_user_time ON user_events(user_id, event_type, timestamp);
```

### Table: `goals` (kept from V1)
Giữ nguyên như V1 — goals vẫn hữu ích cho wealth planning.

### Table: `monthly_reports` (kept with minor update)
Giữ nguyên structure, update `breakdown_by_category` với V2 categories.

### Table: `market_snapshots` (kept)
Giữ nguyên — dùng cho Phase 3B market intelligence.

### Table: `investment_logs` (kept)
Giữ nguyên — dùng cho Phase 4 investment tracking.

### Table: `llm_cache` (kept)
Giữ nguyên — critical cho cost optimization.

### Table: `telegram_updates` (kept from Phase A)
Webhook dedup table, giữ nguyên.
