# CLAUDE.md — Personal CFO Assistant
## Master System Design Document for Implementation

> **Mục đích file này:** Đây là nguồn sự thật (source of truth) cho Claude Code khi implement hệ thống.  
> Đọc toàn bộ file này trước khi viết bất kỳ dòng code nào.  
> Mọi quyết định kỹ thuật đã được thiết kế và giải thích lý do ở đây.
>
> **Document version:** 2.0 (updated sau pivot V1→V2, 24/04/2026)  
> **Phase hiện tại:** 3A — Wealth Foundation

---

## 📚 Documentation References

**Product docs (đọc song song với file này):**
- [`docs/current/strategy.md`](docs/current/strategy.md) — Product vision, positioning, roadmap
- [`docs/current/phase-3a-detailed.md`](docs/current/phase-3a-detailed.md) — **Phase hiện tại**, read TRƯỚC khi code
- [`docs/current/phase-3a-issues.md`](docs/current/phase-3a-issues.md) — GitHub-ready tasks
- [`docs/archive/MIGRATION_NOTES.md`](docs/archive/MIGRATION_NOTES.md) — Context về pivot V1→V2

**Strategy/scaling docs:**
- `docs/strategy/scaling-refactor-A.md` — Phase A refactor (webhook dedup, pool tuning, LLM hot path)
- `docs/strategy/scaling-refactor-B.md` — Layer boundary cleanup

**Rule:** Khi code Phase 3A, đọc **phase-3a-detailed.md** trước. CLAUDE.md là technical spec; phase doc là implementation guide chi tiết.

---

## 0. Bối cảnh & Tầm nhìn sản phẩm

### Positioning (V2)

**Personal CFO cho tầng lớp trung lưu Việt Nam** — AI assistant không chỉ theo dõi chi tiêu, mà quản lý toàn bộ tài sản, tạo báo cáo hàng ngày, và tư vấn đầu tư.

**Không phải:** Finance Assistant / Expense Tracker.  
**Mà là:** Personal CFO với 3 trụ cột:
1. **Wealth Management** — net worth, assets (BĐS, stocks, crypto, cash, vàng)
2. **Cashflow Intelligence** — income + expense (threshold-based, không exhaustive)
3. **Investment Intelligence** — market data, recommendations

### Target User — Ladder of Engagement

App adapt theo 4 wealth levels:
- **Starter** (0-30tr): Tiền mặt, cash-only
- **Young Professional** (30tr-200tr): Beginning investor
- **Mass Affluent** (200tr-1 tỷ): Multi-asset, có BĐS
- **High Net Worth** (1 tỷ+): Full CFO suite

Chi tiết: [`docs/current/strategy.md`](docs/current/strategy.md#-target-user--ladder-of-engagement)

### Giai đoạn hiện tại
Xây dựng cho **1 người dùng (owner)**, chạy trên **Mac Mini M4 (24GB RAM, macOS)**, giao tiếp qua **Telegram Bot** thông qua **OpenClaw**.

### Scale Roadmap
```
Phase 0:  1 user      (Mac Mini local)
Phase 1:  1,000 user  (VPS + Cloud DB)
Phase 2:  10,000 user (Cloud-native)
Phase 3:  100,000 user (Microservices + Kubernetes)
Phase 4:  1,000,000 user (Distributed, multi-region)
```

### Hệ quả kiến trúc QUAN TRỌNG
1. Mọi data model phải có `user_id` — kể cả khi chỉ có 1 user
2. Business logic trong **FastAPI backend**, không trong OpenClaw Skills
3. OpenClaw Skills chỉ là **thin wrapper** gọi API
4. **PostgreSQL** (Docker local) làm primary database
5. Notion chỉ dùng **dashboard đọc** cho owner (sync 1 chiều từ PostgreSQL)

---

## 0.1 Layer contract — ĐỌC TRƯỚC KHI CODE

Đây là kết quả của audit scale tháng 4/2026. Đã apply ở Phase A refactor.

**Runtime path sau Phase A:**
```
webhook → claim update_id → asyncio.create_task → worker → handler → service → adapter
  (≤100ms)    (Postgres dedup)                      (commit)  (logic)  (flush)  (transport)
```

**Contract mỗi layer — không vi phạm:**

| Layer | ĐƯỢC | KHÔNG ĐƯỢC |
|---|---|---|
| `routers/` | Parse HTTP, verify auth, claim `update_id`, enqueue, trả 200 | Business logic, LLM call, Telegram send |
| `workers/` | Mở session, dispatch, commit **một lần** ở boundary | Business logic |
| `bot/handlers/` | Route intent, extract Telegram data, gọi service, format response | `db.commit()`, query DB raw (trừ view-only) |
| `services/` | Business logic thuần, nhận `db`, **flush only**, return domain objects | `db.commit()`, gọi Telegram/LLM trực tiếp, đọc env |
| `adapters/` | Transport: Telegram, Notion, DeepSeek, Claude | Business logic |
| `ports/` | Interface (Protocol) cho `Notifier`, `LLM` — cho DI/test | Implementation |

**Hệ quả cho mọi issue mới:**
- LLM call trong webhook path → phải là background task, không block webhook response.
- Service **không** gọi `db.commit()` — caller (router/worker) sở hữu transaction boundary.
- Service **không** import `telegram_service` trực tiếp — dùng `Notifier` port qua `get_notifier()`.
- Cache LLM: mặc định key kèm `user_id`; chỉ dùng `shared_cache=True` khi prompt không chứa data user.
- Mọi update Telegram **phải** được dedup qua `telegram_updates.update_id` trước khi xử lý.

---

## 1. Stack công nghệ

| Layer | Công nghệ | Lý do |
|---|---|---|
| Agent runtime | OpenClaw (Node.js) | Đã setup, Telegram integration sẵn |
| Agent interface | Telegram Bot | Kênh giao tiếp chính của owner |
| Primary LLM | DeepSeek API | Cost-effective, tiếng Việt tốt, dùng cho categorize / extract / advise |
| Vision LLM | Claude API (Anthropic) | DeepSeek không hỗ trợ Vision — chỉ dùng cho OCR |
| Speech-to-Text | OpenAI Whisper API | Cho voice storytelling |
| Backend | FastAPI (Python 3.11+) | Async, auto-docs |
| Primary Database | PostgreSQL 16 (Docker) | Multi-tenant ready, ACID |
| Cache | Redis | Session, rate limit, LLM response cache, storytelling mode state |
| Message Queue | RabbitMQ / AWS SQS (Phase 2+) | Async job processing |
| Dashboard | Notion (sync 1 chiều) | Owner đọc data dễ dàng |
| Market data — Stocks | vnstock (Python lib) | Dữ liệu chứng khoán VN miễn phí |
| Market data — Crypto | CoinGecko API | Free tier 50 calls/phút |
| Market data — Gold | SJC website scraping | Giá vàng SJC 2-3 lần/ngày |
| Market data — Funds | cafef.vn scraping | NAV các chứng chỉ quỹ |
| Container | Docker + docker-compose | Môi trường nhất quán |

**Đã DEPRECATE (V1 → V2):**
- ~~Gmail API integration~~ — thay bằng **AI Storytelling** (threshold-based)
- ~~SMS forwarding~~ — không còn cần

---

## 2. Cấu trúc thư mục dự án

```
finance-assistant/
│
├── CLAUDE.md                    # File này — đọc trước khi code
├── README.md                    # Setup instructions
│
├── docker-compose.yml           # PostgreSQL + Redis local
├── .env.example                 # Template env vars
├── .env                         # Credentials (gitignored)
├── .gitignore
│
├── docs/                        # Product & technical docs
│   ├── README.md                # Navigation hub
│   ├── current/                 # Active docs
│   │   ├── strategy.md          # Product strategy V2
│   │   ├── phase-1-detailed.md
│   │   ├── phase-2-detailed.md
│   │   ├── phase-3a-detailed.md # ⭐ CURRENT FOCUS
│   │   ├── phase-3a-issues.md
│   │   └── phase-3b-outline.md
│   └── archive/                 # Historical (V1)
│       ├── MIGRATION_NOTES.md
│       └── v1-finance-assistant/
│
├── backend/                     # FastAPI application
│   ├── main.py                  # Entry point
│   ├── config.py                # Settings từ env
│   ├── database.py              # SQLAlchemy async engine
│   ├── requirements.txt
│   │
│   ├── models/                  # SQLAlchemy ORM
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── transaction.py       # (Renamed from expense.py)
│   │   ├── asset.py             # ⭐ NEW — core của V2
│   │   ├── asset_snapshot.py    # ⭐ NEW — daily historical
│   │   ├── income_stream.py     # ⭐ NEW — passive + active income
│   │   ├── goal.py
│   │   ├── report.py
│   │   ├── market_snapshot.py
│   │   ├── investment_log.py
│   │   ├── user_milestone.py    # From Phase 2
│   │   ├── user_event.py        # From Phase 2
│   │   └── telegram_updates.py  # For webhook dedup
│   │
│   ├── schemas/                 # Pydantic schemas
│   │   ├── __init__.py
│   │   ├── asset.py             # ⭐ NEW
│   │   ├── wealth.py            # ⭐ NEW
│   │   ├── transaction.py
│   │   ├── goal.py
│   │   ├── report.py
│   │   └── market.py
│   │
│   ├── routers/                 # API endpoints
│   │   ├── __init__.py
│   │   ├── assets.py            # ⭐ NEW — CRUD assets
│   │   ├── wealth.py            # ⭐ NEW — net worth, breakdown
│   │   ├── transactions.py      # (Renamed expenses.py)
│   │   ├── goals.py
│   │   ├── reports.py
│   │   ├── market.py
│   │   └── ingestion.py         # OCR upload, voice upload
│   │
│   ├── services/                # Business logic
│   │   ├── __init__.py
│   │   │
│   │   ├── wealth/              # ⭐ NEW — wealth management core
│   │   │   ├── __init__.py
│   │   │   ├── asset_service.py
│   │   │   ├── net_worth_calculator.py
│   │   │   ├── threshold_service.py
│   │   │   ├── ladder.py        # Wealth level detection
│   │   │   └── valuation/       # Asset-specific valuation
│   │   │       ├── cash.py
│   │   │       ├── stock.py
│   │   │       ├── real_estate.py
│   │   │       ├── crypto.py
│   │   │       └── gold.py
│   │   │
│   │   ├── capture/             # ⭐ NEW — transaction capture
│   │   │   ├── __init__.py
│   │   │   ├── storytelling_service.py  # LLM extraction
│   │   │   ├── ocr_service.py           # Claude Vision
│   │   │   └── voice_service.py         # Whisper + NLU
│   │   │
│   │   ├── briefing_service.py  # ⭐ NEW — morning briefing
│   │   ├── transaction_service.py # (Renamed expense_service.py)
│   │   ├── goal_service.py
│   │   ├── report_service.py
│   │   ├── market_service.py    # vnstock + scraping + analysis
│   │   ├── notion_sync.py       # Sync PostgreSQL → Notion
│   │   ├── llm_service.py       # LLM routing: DeepSeek / Claude
│   │   ├── milestone_service.py # From Phase 2
│   │   └── empathy_service.py   # From Phase 2
│   │
│   ├── adapters/                # Transport layer
│   │   ├── __init__.py
│   │   ├── telegram_adapter.py
│   │   ├── notion_adapter.py
│   │   ├── deepseek_adapter.py
│   │   ├── claude_adapter.py
│   │   └── whisper_adapter.py   # ⭐ NEW
│   │
│   ├── ports/                   # Interfaces for DI/test
│   │   ├── __init__.py
│   │   ├── notifier.py
│   │   └── llm.py
│   │
│   ├── jobs/                    # Scheduled tasks
│   │   ├── __init__.py
│   │   ├── morning_briefing.py  # ⭐ NEW — 7h sáng adaptive
│   │   ├── daily_snapshot.py    # ⭐ NEW — 23:59 daily
│   │   ├── market_poller.py
│   │   ├── monthly_report.py
│   │   ├── check_milestones.py  # From Phase 2
│   │   └── check_empathy_triggers.py  # From Phase 2
│   │
│   ├── miniapp/                 # Telegram Mini App
│   │   ├── templates/
│   │   │   └── net_worth_dashboard.html  # ⭐ NEW
│   │   ├── static/
│   │   │   ├── css/wealth.css   # ⭐ NEW
│   │   │   └── js/wealth_dashboard.js  # ⭐ NEW
│   │   └── routes.py
│   │
│   └── utils/
│       ├── date_utils.py
│       ├── currency_utils.py    # Format VND (45k, 1.5tr, 1.2 tỷ)
│       └── progress_bar.py      # Unicode progress bars
│
├── content/                     # ⭐ NEW — content files (YAML)
│   ├── asset_categories.yaml    # 6 loại asset + subtypes + icons
│   ├── briefing_templates.yaml  # 4 levels × variations
│   ├── milestone_messages.yaml  # From Phase 2
│   ├── empathy_messages.yaml    # From Phase 2
│   ├── seasonal_calendar.yaml   # From Phase 2
│   └── fun_fact_templates.yaml  # From Phase 2
│
├── alembic/                     # DB migrations
│   ├── versions/
│   └── env.py
│
└── openclaw-skills/             # OpenClaw Skills — thin wrappers
    ├── finance-asset/           # ⭐ NEW — CRUD assets
    ├── finance-wealth/          # ⭐ NEW — net worth display
    ├── finance-storytelling/    # ⭐ NEW — AI extraction
    ├── finance-ocr/
    ├── finance-voice/           # ⭐ NEW — voice input
    ├── finance-report/
    ├── finance-goals/
    └── finance-market/
```

**Folder DEPRECATED (V1 → V2):**
- ~~`services/gmail_service.py`~~ — không còn dùng Gmail
- ~~`jobs/gmail_poller.py`~~ — thay bằng `morning_briefing.py`

---

## 3. Database Schema (PostgreSQL)

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

---

## 4. API Endpoints (FastAPI)

### Base URL: `http://localhost:8000/api/v1`

### Auth
Phase 0: Single API key trong `.env`. Phase 1+: JWT per-user.

### ⭐ Assets (NEW — V2 core)
```
POST   /assets                   # Create asset
GET    /assets                   # List user's assets (filter by type)
GET    /assets/{id}              # Asset detail
PUT    /assets/{id}              # Update (value, metadata)
PUT    /assets/{id}/value        # Update current_value only (creates snapshot)
DELETE /assets/{id}              # Soft delete (mark sold)
```

### ⭐ Wealth (NEW)
```
GET    /wealth/overview          # Net worth + breakdown + change
GET    /wealth/trend?days=30|90|365  # Historical net worth
GET    /wealth/level             # User's wealth level + next milestone
GET    /wealth/breakdown         # Detailed by asset type
```

### Transactions (RENAMED from /expenses)
```
POST   /transactions             # Create manual transaction
GET    /transactions             # List (filter: month, category, source)
GET    /transactions/{id}        # Detail
PUT    /transactions/{id}        # Update (category, amount)
DELETE /transactions/{id}        # Soft delete
GET    /transactions/summary     # Monthly aggregates
```

### ⭐ Storytelling (NEW)
```
POST   /storytelling/extract     # User story text → extracted transactions
POST   /storytelling/confirm     # Confirm extracted transactions → save DB
```

### Goals
```
POST   /goals
GET    /goals
PUT    /goals/{id}
PUT    /goals/{id}/progress
DELETE /goals/{id}
```

### Income Streams ⭐ NEW
```
POST   /income-streams           # Add new income source
GET    /income-streams           # List active streams
PUT    /income-streams/{id}
DELETE /income-streams/{id}
POST   /users/income             # Legacy: set monthly_income
```

### Reports
```
GET    /reports/monthly?month=2026-03
GET    /reports/history
POST   /reports/generate
```

### Ingestion (UPDATED)
```
POST   /ingestion/ocr            # Upload image → OCR → transaction
POST   /ingestion/voice          # Upload audio → Whisper → transaction
POST   /ingestion/manual         # Manual transaction entry
```

**DEPRECATED (V1):**
- ~~`POST /ingestion/gmail/sync`~~ — Gmail no longer integrated

### Market
```
GET    /market/snapshot
GET    /market/history?asset=VNINDEX
POST   /market/advice
```

### Mini App (Telegram Web App)
```
GET    /miniapp/dashboard        # Serve HTML
GET    /miniapp/api/wealth/overview  # For Mini App JS
GET    /miniapp/api/wealth/trend?days=...
```

---

## 5. OpenClaw Skills Design

### Nguyên tắc quan trọng
**Skills KHÔNG chứa business logic.** Chỉ làm 3 việc:
1. Parse user message thành structured args
2. Gọi Backend API
3. Format response về Telegram

### Skill: `finance-asset` ⭐ NEW
**Triggers:**
- "thêm tài sản", "add asset", "tôi có ..."
- "mua cổ phiếu VNM 100 cổ giá 45k"
- "bán nhà được 3 tỷ"
- "cập nhật giá trị BĐS"

**Gọi API:** `POST /api/v1/assets`, `PUT /api/v1/assets/{id}/value`

### Skill: `finance-wealth` ⭐ NEW
**Triggers:**
- "tài sản của tôi", "net worth"
- "tôi có bao nhiêu tiền"
- "tổng giá trị tài sản"
- User tap nút "📊 Dashboard" từ briefing

**Gọi API:** `GET /api/v1/wealth/overview`, `GET /api/v1/wealth/trend`

### Skill: `finance-storytelling` ⭐ NEW
**Triggers:**
- User tap nút "💬 Kể chuyện" từ morning briefing
- "/kechuyen", "/story"
- Free-form text sau khi vào storytelling mode

**Flow:**
```
User message → POST /api/v1/storytelling/extract
→ Backend gọi DeepSeek → trả về extracted transactions
→ Skill hỏi confirm qua Telegram (inline buttons)
→ User confirm → POST /api/v1/storytelling/confirm
```

### Skill: `finance-ocr`
**Triggers:** User gửi file ảnh bất kỳ

**Quan trọng — Model override:**
```json
"finance-ocr": {
  "imageModel": "claude-opus-4-7"
}
```

**Flow:**
```
Nhận ảnh → POST /api/v1/ingestion/ocr (multipart)
→ Backend gọi Claude Vision → trả về JSON
→ Skill hỏi confirm → POST /api/v1/transactions
```

### Skill: `finance-voice` ⭐ NEW
**Triggers:** User gửi voice message

**Flow:**
```
Nhận audio → POST /api/v1/ingestion/voice
→ Backend gọi Whisper → transcript
→ NLU parse → extracted data
→ Confirm với user
```

### Skill: `finance-report`
Giữ nguyên V1 + thêm option "Báo cáo wealth".

### Skill: `finance-goals`
Giữ nguyên V1.

### Skill: `finance-market`
Giữ nguyên V1 — sẽ enhance ở Phase 3B.

**DEPRECATED:**
- ~~Skill `finance-expense` với Gmail triggers~~ — thay bằng `finance-storytelling`

---

## 6. Service Layer — Business Logic

### ⭐ `wealth/asset_service.py` (NEW — core)

**`create_asset(user_id, asset_type, name, initial_value, ...) → Asset`**
- Tạo asset + first snapshot
- Auto-compute wealth_level sau khi create
- Track event `asset_added`

**`update_current_value(asset_id, user_id, new_value) → Asset`**
- Update value + create/update snapshot today
- Không duplicate snapshot nếu đã có hôm nay

**`get_user_assets(user_id, include_inactive=False) → List[Asset]`**

**`soft_delete(asset_id, user_id, sold_value=None)`**
- Mark is_active=False, preserve history

### ⭐ `wealth/net_worth_calculator.py` (NEW)

**`calculate(user_id) → NetWorthBreakdown`**
- Sum current_value của active assets
- Breakdown by asset_type
- Identify largest asset

**`calculate_historical(user_id, target_date) → Decimal`**
- Query latest snapshot ≤ target_date per asset
- DISTINCT ON (asset_id) cho performance

**`calculate_change(user_id, period) → NetWorthChange`**
- Periods: "day" | "week" | "month" | "year"
- Return absolute + percentage change

**⚠️ CRITICAL:** Dùng `Decimal`, không dùng `float` cho mọi money calculation.

### ⭐ `wealth/ladder.py` (NEW)

**`detect_level(net_worth) → WealthLevel`**
- 0-30tr → STARTER
- 30tr-200tr → YOUNG_PROFESSIONAL
- 200tr-1 tỷ → MASS_AFFLUENT
- 1 tỷ+ → HIGH_NET_WORTH

**`next_milestone(net_worth) → (target_amount, target_level)`**

### ⭐ `wealth/threshold_service.py` (NEW)

**`compute_thresholds(monthly_income) → (micro, major)`**
- Income-based adaptive thresholds
- <15tr → (100k, 1tr)
- 15-30tr → (200k, 2tr)
- 30-60tr → (300k, 3tr)
- 60tr+ → (500k, 5tr)

### ⭐ `briefing_service.py` (NEW)

**`generate_for_user(user) → str`**
- Load template theo wealth_level
- Compute net worth + change
- Format với YAML template
- Append storytelling prompt
- Output < 800 chars (mobile screen)

**Templates file:** `content/briefing_templates.yaml`

### ⭐ `capture/storytelling_service.py` (NEW)

**`extract_from_story(story, user_id, threshold) → dict`**
- Call DeepSeek với STORYTELLING_PROMPT
- Output: `transactions[]`, `needs_clarification[]`, `ignored_small[]`
- **Chỉ extract > threshold** — quan trọng!
- Log raw input/output để debug

**Prompt file:** `backend/prompts/storytelling_prompt.py`

### ⭐ `capture/voice_service.py` (NEW)

**`transcribe_and_parse(audio_bytes, user_id) → dict`**
- Whisper transcribe tiếng Việt
- Pass transcript vào storytelling_service
- Support context resolution ("như hôm qua")

### `capture/ocr_service.py` (kept, minor update)

**`parse_receipt_image(image_bytes) → dict`**
- Claude Vision với prompt extract transaction
- Confidence thresholds:
  - >0.7 → auto-save
  - 0.3-0.7 → ask user confirm
  - <0.3 → reject
- Cache by image hash (Redis)

### `transaction_service.py` (kept with updates)

**`create_transaction(..., source, confidence, raw_input, verified_by_user)`**
- New fields từ V2
- Trigger wealth_level recompute nếu là category investment

**`categorize_transaction(merchant, description, amount) → category`**
- Check learned rules (user-specific) trước
- Fallback default rules (YAML)
- Last resort: LLM

### `llm_service.py` (kept)

**LLM Routing Rules (updated):**
```python
USE_CLAUDE = ["ocr"]  # Vision only

USE_DEEPSEEK = [
    "storytelling_extract",
    "categorize",
    "briefing_generate",  # Phase 3B sẽ có tin tức market
    "report_text",
    "investment_advice",
    "intent_detection",
]

USE_WHISPER = ["voice_transcribe"]  # OpenAI Whisper API
```

### `market_service.py` (kept)
Giữ nguyên V1 — dùng vnstock + cafef scraping. Enhance ở Phase 3B với CoinGecko + SJC scraping.

### `milestone_service.py` (from Phase 2)
Giữ nguyên, thêm milestones mới cho wealth:
- `savings_1m`, `savings_10m`, `savings_100m`, `savings_1b`
- `first_asset_added`
- `asset_diversity_3_types` (có 3 loại asset trở lên)

**DEPRECATED:**
- ~~`gmail_service.py`~~ — toàn bộ file bỏ

---

## 7. Jobs (Scheduled Tasks)

### Cron Schedule
```python
SCHEDULES = {
    # V2 core jobs
    "morning_briefing":     "*/15 * * * *",     # Mỗi 15 phút (adaptive timing)
    "daily_snapshot":       "59 23 * * *",      # 23:59 daily (VN time)
    
    # From Phase 2
    "check_milestones":     "0 8 * * *",        # 8:00 sáng daily
    "check_empathy":        "0 7-22 * * *",     # Mỗi giờ, 7-22h
    "weekly_fun_facts":     "0 19 * * 0",       # Chủ nhật 19:00
    "seasonal_notifier":    "0 8 * * *",        # 8:00 daily check calendar
    
    # Market & reports
    "market_snapshot":      "0 8 * * *",        # 8:00 sáng
    "monthly_report":       "0 9 1 * *",        # 9:00 ngày 1 tháng
}
```

### ⭐ `morning_briefing.py` (NEW)
```
1. Query active users (30 ngày), briefing_enabled=True
2. Với mỗi user: check nếu trong cửa sổ 15p tới briefing_time
3. Check chưa gửi hôm nay
4. Generate briefing qua briefing_service
5. Send Telegram với inline keyboard
6. Track event morning_briefing_sent
7. Rate limit: 1 msg/second
```

### ⭐ `daily_snapshot.py` (NEW)
```
1. Query all active assets
2. Skip nếu đã có snapshot hôm nay (user đã update)
3. Create snapshot với source="auto_daily"
4. Batch insert cho performance
5. Log: số snapshots created
```

### `market_poller.py` (kept)
Giữ nguyên V1.

### `monthly_report.py` (kept)
Giữ nguyên + update để include wealth summary.

**DEPRECATED:**
- ~~`gmail_poller.py`~~ — removed entirely

---

## 8. Notion Sync (Secondary — Dashboard only)

**Sync 1 chiều: PostgreSQL → Notion**

### 6 Notion Databases cần tạo
```
NOTION_ASSETS_DB_ID=         # ⭐ NEW
NOTION_TRANSACTIONS_DB_ID=   # (renamed from EXPENSES)
NOTION_GOALS_DB_ID=
NOTION_REPORTS_DB_ID=
NOTION_MARKET_DB_ID=
NOTION_INVESTMENT_LOG_DB_ID=
```

### Schema Notion `Assets` DB ⭐ NEW
```
Name (Title)
Type (Select: Cash/Stock/RealEstate/Crypto/Gold/Other)
Current Value (Number — VND)
Change % (Number — formula from initial vs current)
Acquired Date (Date)
Status (Select: Active/Sold)
```

### Schema Notion `Transactions` DB (UPDATED)
```
Date (Date)
Amount (Number — VND)
Merchant (Text)
Category (Select)
Source (Select: Manual/Storytelling/OCR/Voice/WrapUp)
Month (Text)
Note (Text)
Needs Review (Checkbox)
```

---

## 9. Environment Variables

```bash
# === Backend ===
ENVIRONMENT=development
PORT=8000
INTERNAL_API_KEY=

# === Database ===
DATABASE_URL=postgresql+asyncpg://finance:password@localhost:5432/finance_db

# === Redis (Phase 0+) ===
REDIS_URL=redis://localhost:6379/0

# === LLM APIs ===
DEEPSEEK_API_KEY=                # Primary LLM
DEEPSEEK_BASE_URL=https://api.deepseek.com
ANTHROPIC_API_KEY=               # Vision (OCR)

# === V2 NEW: Speech-to-Text ===
OPENAI_API_KEY=                  # Whisper cho voice storytelling

# === V2 NEW: Wealth defaults ===
PRIMARY_CURRENCY=VND
DEFAULT_BRIEFING_TIME=07:00
DEFAULT_EXPENSE_THRESHOLD_MICRO=200000
DEFAULT_EXPENSE_THRESHOLD_MAJOR=2000000

# === Notion ===
NOTION_API_KEY=
NOTION_ASSETS_DB_ID=             # ⭐ NEW
NOTION_TRANSACTIONS_DB_ID=
NOTION_GOALS_DB_ID=
NOTION_REPORTS_DB_ID=
NOTION_MARKET_DB_ID=
NOTION_INVESTMENT_LOG_DB_ID=

# === Telegram ===
TELEGRAM_BOT_TOKEN=
OWNER_TELEGRAM_ID=

# === OpenClaw Skills ===
FINANCE_API_URL=http://localhost:8000/api/v1
FINANCE_API_KEY=

# === Market Data (Phase 3B) ===
# SSI_API_KEY=                   # Phase 3B
# COINGECKO_API_KEY=             # Phase 3B (optional, free tier không cần)
# GOOGLE_PLACES_API_KEY=         # Optional, location feature
```

**DEPRECATED (V1):**
- ~~`GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REDIRECT_URI`~~

---

## 10. docker-compose.yml

Giữ nguyên V1 setup — PostgreSQL + Redis đã đủ cho V2.

---

## 11. Dependencies (requirements.txt)

```
# Web framework
fastapi>=0.110.0
uvicorn[standard]>=0.27.0
python-multipart>=0.0.9

# Database
sqlalchemy[asyncio]>=2.0.0
asyncpg>=0.29.0
alembic>=1.13.0

# Cache
redis>=5.0.0
hiredis>=2.3.0

# Scheduling
apscheduler>=3.10.0

# LLM
anthropic>=0.25.0              # Claude Vision
openai>=1.0.0                  # DeepSeek (OpenAI-compat) + Whisper

# V2 NEW: Content loading
pyyaml>=6.0

# V2 NEW: Lunar calendar (cho Tết seasonal content)
lunardate>=0.2.0

# Notion
notion-client>=2.2.0

# Market data (V1 + V2)
vnstock>=0.3.0
requests>=2.31.0
beautifulsoup4>=4.12.0
lxml>=5.0.0
httpx>=0.27.0                  # Async HTTP

# Utils
python-dotenv>=1.0.0
pydantic-settings>=2.0.0
python-dateutil>=2.8.0
Pillow>=10.0.0                 # Image processing cho OCR

# Dev
pytest>=8.0.0
pytest-asyncio>=0.23.0
```

**DEPRECATED:**
- ~~`google-auth-oauthlib`, `google-auth-httplib2`, `google-api-python-client`~~

---

## 12. Build Order — Phase 3A (V2)

> **Phase 0-2 đã complete.** Phase hiện tại là Phase 3A — Wealth Foundation.  
> **Chi tiết đầy đủ:** [`docs/current/phase-3a-detailed.md`](docs/current/phase-3a-detailed.md)  
> **Issues GitHub:** [`docs/current/phase-3a-issues.md`](docs/current/phase-3a-issues.md)

### Phase 3A — 4 tuần

**Tuần 1: Asset Data Model & Manual Entry** (Issues P3A-1 → P3A-9)
```
- [ ] P3A-1: Migrations cho assets, asset_snapshots, income_streams
- [ ] P3A-2: Models + asset_categories.yaml
- [ ] P3A-3: AssetService (CRUD + soft delete)
- [ ] P3A-4: NetWorthCalculator
- [ ] P3A-5: Wealth Level detection
- [ ] P3A-6: Asset wizard: Cash flow
- [ ] P3A-7: Asset wizard: Stock flow
- [ ] P3A-8: Asset wizard: Real Estate flow
- [ ] P3A-9: Integrate "first asset" vào onboarding
```

**Tuần 2: Morning Briefing** (Issues P3A-10 → P3A-15)
```
- [ ] P3A-10: briefing_templates.yaml (4 levels)
- [ ] P3A-11: BriefingFormatter (ladder-aware)
- [ ] P3A-12: morning_briefing_job (scheduled)
- [ ] P3A-13: daily_snapshot_job
- [ ] P3A-14: Briefing inline keyboard
- [ ] P3A-15: Analytics tracking
```

**Tuần 3: Storytelling Expense** (Issues P3A-16 → P3A-20)
```
- [ ] P3A-16: threshold_service (income-based)
- [ ] P3A-17: Storytelling LLM prompt (30+ test samples)
- [ ] P3A-18: Storytelling handler (text + voice)
- [ ] P3A-19: Confirmation UI
- [ ] P3A-20: Integration với briefing keyboard
```

**Tuần 4: Visualization & Testing** (Issues P3A-21 → P3A-26)
```
- [ ] P3A-21: Mini App dashboard HTML/CSS
- [ ] P3A-22: /api/wealth/overview endpoint
- [ ] P3A-23: Chart.js integration (pie + trend)
- [ ] P3A-24: Milestone display cho starter
- [ ] P3A-25: 7-user testing protocol
- [ ] P3A-26: Bug fixes from testing
```

### Phase 3B — Market Intelligence (sau validation 3A)
Chi tiết: [`docs/current/phase-3b-outline.md`](docs/current/phase-3b-outline.md)

---

## 13. Coding Conventions

### Python
- **async/await** cho tất cả I/O (DB, API, file)
- Type hints bắt buộc
- Pydantic cho data validation
- Exception handling: raise cụ thể, không swallow silently
- **Logging**: Python `logging` module, không `print()`

### Money Handling ⭐ CRITICAL cho V2
- **LUÔN dùng `Decimal`**, không dùng `float` cho money
- Import: `from decimal import Decimal`
- DB columns: `NUMERIC(20, 2)` cho money, `NUMERIC(15, 2)` cho amount nhỏ
- Format output qua `currency_utils.format_money_short/full`

### API Design
- Response format thống nhất:
```python
{"data": {...}, "error": null}
{"data": null, "error": {"code": "ASSET_NOT_FOUND", "message": "..."}}
```
- HTTP status codes chuẩn: 200, 201, 400, 401, 404, 422, 500
- Tất cả endpoints nhận `user_id` qua API key lookup / JWT

### Security
- **KHÔNG** hardcode credentials
- **KHÔNG** commit `.env`
- Secrets qua env vars + `config.py`
- SQLAlchemy ORM hoặc parameterized queries
- ⭐ V2: Wealth data sensitivity cao — consider encryption-at-rest cho `assets.current_value` khi scale

### Content Files (YAML) ⭐ NEW V2
- User-facing messages → YAML files trong `content/`
- Dễ edit không cần deploy
- Test content bằng cách đọc to — nếu sến súa, rewrite

### Testing
- Unit test cho mỗi service method
- **Integration test cho LLM prompts** (critical cho storytelling)
- Prompt test suite: 30+ sample inputs với expected outputs
- Mỗi wizard cần end-to-end test

---

## 14. Scale Roadmap — Khi nào làm gì

### Phase 0 → Phase 1 (khi có ~100 users beta)
```
- [ ] Deploy FastAPI lên VPS
- [ ] PostgreSQL managed DB (Supabase)
- [ ] JWT authentication
- [ ] Telegram Bot public
- [ ] Rate limiting
```

### Phase 1 → Phase 2 (~1,000 users)
```
- [ ] Celery workers cho scheduled jobs
- [ ] Redis cluster cho cache scale
- [ ] Web dashboard (Next.js PWA)
- [ ] Subscription model (VNPay / Stripe)
- [ ] Sentry + Grafana
- [ ] Phase 5 Behavioral Engine (Financial DNA, Twin)
```

### Phase 2 → Phase 3 (~10,000 users)
```
- [ ] Kubernetes deployment
- [ ] Microservices: Wealth / Capture / Intelligence / Notification
- [ ] Read replicas
- [ ] Multi-region (Singapore primary)
- [ ] Household mode (vợ chồng cùng quản lý)
```

### Phase 3 → Phase 4 (~100k+ users)
```
- [ ] Horizontal auto-scaling
- [ ] Global load balancing
- [ ] LLM fine-tuning cho categorization
- [ ] Advanced analytics (ClickHouse)
- [ ] Zalo Mini App mass market
```

---

## 15. Cost Tracking

| Phase | Users | Infra/tháng | LLM/tháng | Total/tháng |
|---|---|---|---|---|
| Phase 0 | 1 | $0 (Mac Mini) | ~$5 | ~$5 |
| Phase 1 | 1,000 | ~$75 | ~$200 | ~$275 |
| Phase 2 | 10,000 | ~$700 | ~$1,500 | ~$2,200 |
| Phase 3 | 100,000 | ~$4,000 | ~$10,000 | ~$14,000 |
| Phase 4 | 1,000,000 | ~$25,000 | ~$80,000 | ~$105,000 |

**V2 cost optimizations:**
- Storytelling LLM calls cache aggressive (same-user same-day cache)
- DeepSeek cho text, Claude chỉ cho Vision
- Whisper cost: ~$0.006/phút → cache transcripts theo hash
- Market data: vnstock/CoinGecko/cafef free → no LLM cost
- Briefing generation: pure template + data → no LLM needed (chỉ Phase 3B market summary dùng LLM)

**Pricing tier V2 (justify LLM cost):**
- Free: Basic tracking, 1 asset type
- Pro (149k/tháng): All assets, morning briefing, DNA
- CFO (399k/tháng): Rental, advanced analytics, investment twin

---

## 🚨 Breaking Changes V1 → V2

**Khi implement Phase 3A, những thay đổi này cần được handle:**

### Database
- Table rename: `expenses` → `transactions`
- Drop column: `expenses.gmail_message_id`
- Add columns to `users`: wealth_level, expense_threshold_*, briefing_*
- New tables: `assets`, `asset_snapshots`, `income_streams`

### Code
- Folder rename: `services/expense_service.py` → `services/transaction_service.py`
- Files removed: `gmail_service.py`, `jobs/gmail_poller.py`
- Import paths: update tất cả references tới `expense` → `transaction`

### Config
- Remove: `GMAIL_*` env vars
- Add: `OPENAI_API_KEY`, wealth defaults

### Migration Plan
```
Step 1: Create migration adding new tables (assets, asset_snapshots, income_streams)
Step 2: Create migration adding new columns to users + transactions
Step 3: Rename table expenses → transactions (+ code updates)
Step 4: Drop GMAIL columns (verify no code uses it)
Step 5: Update .env, remove Gmail services
```

---

*Document version: 2.0*  
*Last major update: 24/04/2026 — Pivot Finance Assistant → Personal CFO*  
*Cập nhật khi có thay đổi kiến trúc quan trọng*  
*Khi implement, comment vào đây nếu phát hiện design cần điều chỉnh*
