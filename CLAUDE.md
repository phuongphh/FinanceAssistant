# CLAUDE.md — Personal Finance AI Assistant
## Master System Design Document for Implementation

> **Mục đích file này:** Đây là nguồn sự thật (source of truth) cho Claude Code khi implement hệ thống.
> Đọc toàn bộ file này trước khi viết bất kỳ dòng code nào.
> Mọi quyết định kỹ thuật đã được thiết kế và giải thích lý do ở đây.

---

## 0. Bối cảnh & Tầm nhìn sản phẩm

### Giai đoạn hiện tại
Xây dựng trợ lý tài chính cá nhân cho **1 người dùng (owner)**, chạy trên **Mac Mini M4 (24GB RAM, macOS)**, giao tiếp qua **Telegram Bot** thông qua **OpenClaw** (open-source AI agent platform).

### Tầm nhìn dài hạn
Sau khi validate với cá nhân, sản phẩm sẽ được mở rộng thành **multi-tenant SaaS** phục vụ mass-user với lộ trình:
```
Phase 0:  1 user      (Mac Mini local)
Phase 1:  1,000 user  (VPS + Cloud DB)
Phase 2:  10,000 user (Cloud-native)
Phase 3:  100,000 user (Microservices + Kubernetes)
Phase 4:  1,000,000 user (Distributed, multi-region)
```

### Hệ quả kiến trúc QUAN TRỌNG
**Vì tầm nhìn scale này, ngay từ Phase 0 phải tuân thủ:**
1. Mọi data model phải có `user_id` — kể cả khi chỉ có 1 user
2. Business logic nằm trong **FastAPI backend**, không trong OpenClaw Skills
3. OpenClaw Skills chỉ là **thin wrapper** gọi API
4. Dùng **PostgreSQL** (Docker local) làm primary database, không phải Notion
5. Notion chỉ dùng làm **dashboard đọc** cho owner — sync 1 chiều từ PostgreSQL

---

## 1. Stack công nghệ

| Layer | Công nghệ | Lý do |
|---|---|---|
| Agent runtime | OpenClaw (Node.js) | Đã setup, Telegram integration sẵn |
| Agent interface | Telegram Bot | Kênh giao tiếp chính của owner |
| Primary LLM | DeepSeek API | Cost-effective, tiếng Việt tốt |
| Vision LLM | Claude API (Anthropic) | DeepSeek không hỗ trợ Vision — chỉ dùng cho OCR |
| Backend | FastAPI (Python 3.11+) | Async, auto-docs, dễ containerize |
| Primary Database | PostgreSQL 16 (Docker) | Multi-tenant ready, ACID, dễ migrate lên cloud |
| Cache | Redis (Phase 1+) | Session, rate limit, LLM response cache |
| Message Queue | RabbitMQ / AWS SQS (Phase 2+) | Async job processing |
| Dashboard | Notion (sync 1 chiều) | Owner đọc data dễ dàng |
| Market data | vnstock (Python lib) | Dữ liệu chứng khoán VN miễn phí |
| Scraping | requests + BeautifulSoup | cafef.vn cho chứng chỉ quỹ |
| Container | Docker + docker-compose | Môi trường nhất quán, dễ deploy |

---

## 2. Cấu trúc thư mục dự án

```
finance-assistant/
│
├── CLAUDE.md                    # File này — đọc trước khi code
│
├── docker-compose.yml           # PostgreSQL + Redis local
├── .env.example                 # Template env vars (KHÔNG commit .env thật)
├── .env                         # Credentials thật (gitignore)
├── .gitignore
│
├── backend/                     # FastAPI application
│   ├── main.py                  # Entry point, app init, router mount
│   ├── config.py                # Settings từ env vars (pydantic BaseSettings)
│   ├── database.py              # SQLAlchemy engine, session factory
│   ├── requirements.txt
│   │
│   ├── models/                  # SQLAlchemy ORM models
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── expense.py
│   │   ├── goal.py
│   │   ├── report.py
│   │   ├── market_snapshot.py
│   │   └── investment_log.py
│   │
│   ├── schemas/                 # Pydantic schemas (request/response)
│   │   ├── __init__.py
│   │   ├── expense.py
│   │   ├── goal.py
│   │   ├── report.py
│   │   └── market.py
│   │
│   ├── routers/                 # API endpoints, grouped by domain
│   │   ├── __init__.py
│   │   ├── expenses.py          # CRUD expenses
│   │   ├── goals.py             # CRUD goals, income
│   │   ├── reports.py           # Generate & fetch reports
│   │   ├── market.py            # Market data & investment advice
│   │   └── ingestion.py         # Gmail sync trigger, OCR upload
│   │
│   ├── services/                # Business logic layer
│   │   ├── __init__.py
│   │   ├── expense_service.py   # Categorization, dedup, budget alert
│   │   ├── gmail_service.py     # Gmail API integration
│   │   ├── ocr_service.py       # Claude Vision OCR
│   │   ├── report_service.py    # Report generation logic
│   │   ├── market_service.py    # vnstock + scraping + analysis
│   │   ├── notion_sync.py       # Sync PostgreSQL → Notion (1 chiều)
│   │   └── llm_service.py       # LLM routing: DeepSeek vs Claude
│   │
│   ├── jobs/                    # Scheduled/background jobs
│   │   ├── gmail_poller.py      # Cron: poll Gmail mỗi 30 phút
│   │   ├── market_poller.py     # Cron: snapshot market 8:00 sáng
│   │   └── monthly_report.py   # Cron: báo cáo ngày 1 hàng tháng
│   │
│   └── utils/
│       ├── date_utils.py
│       └── currency_utils.py    # Format VND
│
└── openclaw-skills/             # OpenClaw Skills — thin wrappers
    ├── finance-expense/
    │   ├── SKILL.md
    │   └── expense_cli.py       # Nhận args → gọi backend API
    ├── finance-ocr/
    │   ├── SKILL.md
    │   └── ocr_cli.py
    ├── finance-report/
    │   ├── SKILL.md
    │   └── report_cli.py
    ├── finance-goals/
    │   ├── SKILL.md
    │   └── goals_cli.py
    └── finance-market/
        ├── SKILL.md
        └── market_cli.py
```

---

## 3. Database Schema (PostgreSQL)

### Nguyên tắc schema
- **Mọi table đều có `user_id` (UUID, NOT NULL, indexed)**
- Dùng UUID cho primary keys — tránh conflict khi merge data
- `created_at` và `updated_at` trên mọi table
- Soft delete với `deleted_at` — không xóa cứng data

### Table: `users`
```sql
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_id     BIGINT UNIQUE NOT NULL,    -- Telegram user ID
    telegram_handle VARCHAR(255),
    display_name    VARCHAR(255),
    timezone        VARCHAR(50) DEFAULT 'Asia/Ho_Chi_Minh',
    currency        VARCHAR(10) DEFAULT 'VND',
    monthly_income  NUMERIC(15,2),             -- Thu nhập tháng (tự khai)
    is_active       BOOLEAN DEFAULT true,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ                -- Soft delete
);
```

### Table: `expenses`
```sql
CREATE TABLE expenses (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    amount          NUMERIC(15,2) NOT NULL,
    currency        VARCHAR(10) DEFAULT 'VND',
    merchant        VARCHAR(500),
    category        VARCHAR(100) NOT NULL,
    -- Categories: 'food_drink' | 'transport' | 'shopping' | 'health'
    --             'entertainment' | 'utilities' | 'investment'
    --             'savings' | 'other' | 'needs_review'
    source          VARCHAR(50) NOT NULL,
    -- Sources: 'gmail' | 'ocr' | 'manual' | 'bank_sync'
    expense_date    DATE NOT NULL,
    month_key       VARCHAR(7) NOT NULL,       -- Format: '2026-03' (để query nhanh)
    note            TEXT,
    raw_data        JSONB,                     -- Raw email/OCR data gốc, dùng debug
    needs_review    BOOLEAN DEFAULT false,     -- True nếu parse không chắc chắn
    gmail_message_id VARCHAR(255),             -- Dedup Gmail
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ
);

CREATE INDEX idx_expenses_user_id ON expenses(user_id);
CREATE INDEX idx_expenses_month_key ON expenses(user_id, month_key);
CREATE INDEX idx_expenses_category ON expenses(user_id, category);
CREATE INDEX idx_expenses_gmail_id ON expenses(gmail_message_id) WHERE gmail_message_id IS NOT NULL;
```

### Table: `goals`
```sql
CREATE TABLE goals (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id),
    goal_name           VARCHAR(500) NOT NULL,
    target_amount       NUMERIC(15,2) NOT NULL,
    current_amount      NUMERIC(15,2) DEFAULT 0,
    deadline            DATE,
    priority            VARCHAR(20) DEFAULT 'medium',
    -- Priorities: 'high' | 'medium' | 'low'
    is_active           BOOLEAN DEFAULT true,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW(),
    deleted_at          TIMESTAMPTZ
);

CREATE INDEX idx_goals_user_id ON goals(user_id);
```

### Table: `monthly_reports`
```sql
CREATE TABLE monthly_reports (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id),
    month_key           VARCHAR(7) NOT NULL,   -- '2026-03'
    total_expense       NUMERIC(15,2) NOT NULL,
    total_income        NUMERIC(15,2),
    savings_amount      NUMERIC(15,2),
    savings_rate        NUMERIC(5,2),          -- Phần trăm
    breakdown_by_category JSONB NOT NULL,      -- {"food_drink": 2800000, ...}
    vs_previous_month   JSONB,                 -- {"total_diff_pct": 12.5, ...}
    goal_progress       JSONB,                 -- Snapshot tiến độ goals
    report_text         TEXT,                  -- Full text report gửi Telegram
    generated_at        TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, month_key)
);

CREATE INDEX idx_reports_user_month ON monthly_reports(user_id, month_key);
```

### Table: `market_snapshots`
```sql
CREATE TABLE market_snapshots (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_date   DATE NOT NULL,
    asset_code      VARCHAR(50) NOT NULL,      -- 'VNINDEX', 'VN30', 'DCDS', ...
    asset_type      VARCHAR(50) NOT NULL,
    -- Types: 'index' | 'stock' | 'fund' | 'real_estate'
    asset_name      VARCHAR(500),
    price           NUMERIC(15,4),
    change_1d_pct   NUMERIC(8,4),              -- % thay đổi so hôm qua
    change_1w_pct   NUMERIC(8,4),
    change_1m_pct   NUMERIC(8,4),
    extra_data      JSONB,                     -- NAV, volume, v.v.
    source_url      TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(snapshot_date, asset_code)
);

CREATE INDEX idx_market_date ON market_snapshots(snapshot_date DESC);
CREATE INDEX idx_market_asset ON market_snapshots(asset_code, snapshot_date DESC);
```

### Table: `investment_logs`
```sql
CREATE TABLE investment_logs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id),
    log_date            DATE NOT NULL,
    market_context      JSONB NOT NULL,        -- Snapshot thị trường lúc đó
    user_financial_context JSONB NOT NULL,     -- Cash, goals, risk profile lúc đó
    recommendation      TEXT NOT NULL,         -- Full text gợi ý
    action_taken        TEXT,                  -- User ghi lại sau
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_investment_logs_user ON investment_logs(user_id, log_date DESC);
```

### Table: `llm_cache`
```sql
-- Cache LLM responses để giảm cost ở scale lớn
CREATE TABLE llm_cache (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cache_key       VARCHAR(500) UNIQUE NOT NULL,  -- hash(prompt)
    model           VARCHAR(100) NOT NULL,
    prompt_hash     VARCHAR(64) NOT NULL,
    response        TEXT NOT NULL,
    tokens_used     INTEGER,
    expires_at      TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_llm_cache_key ON llm_cache(cache_key);
CREATE INDEX idx_llm_cache_expires ON llm_cache(expires_at);
```

---

## 4. API Endpoints (FastAPI)

### Base URL: `http://localhost:8000/api/v1`

### Auth (Phase 0: simple API key, Phase 1+: JWT)
```
Header: X-API-Key: <INTERNAL_API_KEY>
```
Phase 0 dùng single API key trong `.env`. Phase 1 chuyển sang JWT per-user.

### Expenses
```
POST   /expenses              # Tạo expense mới
GET    /expenses              # List expenses (filter: month, category)
GET    /expenses/{id}         # Chi tiết 1 expense
PUT    /expenses/{id}         # Update (sửa category, amount)
DELETE /expenses/{id}         # Soft delete
GET    /expenses/summary      # Tổng hợp theo tháng/category
```

### Goals
```
POST   /goals                 # Tạo goal mới
GET    /goals                 # List goals active
PUT    /goals/{id}            # Update goal
PUT    /goals/{id}/progress   # Cập nhật current_amount
DELETE /goals/{id}            # Soft delete
POST   /users/income          # Set/update monthly income
```

### Reports
```
GET    /reports/monthly?month=2026-03   # Lấy/generate báo cáo tháng
GET    /reports/history                 # Lịch sử các báo cáo
POST   /reports/generate                # Force regenerate
```

### Ingestion
```
POST   /ingestion/gmail/sync            # Trigger Gmail sync ngay
POST   /ingestion/ocr                   # Upload ảnh → OCR → trả JSON
POST   /ingestion/manual                # Nhập expense tay qua text
```

### Market
```
GET    /market/snapshot                 # Snapshot mới nhất
GET    /market/history?asset=VNINDEX    # Lịch sử giá
POST   /market/advice                   # Generate investment advice
```

---

## 5. OpenClaw Skills Design

### Nguyên tắc quan trọng
**Skills KHÔNG chứa business logic.** Chỉ làm 3 việc:
1. Parse user message thành structured args
2. Gọi Backend API
3. Format response về Telegram

### Cấu trúc mỗi SKILL.md
```markdown
---
name: finance-[domain]
description: [Mô tả ngắn, viết như mô tả cho coworker]
triggers:
  - [pattern trigger]
env:
  - FINANCE_API_URL
  - FINANCE_API_KEY
---

# Finance [Domain] Skill

## Khi nào dùng skill này
[Liệt kê các intent cụ thể]

## Cách thực thi
[Step-by-step runbook rõ ràng]

## Output format
[Format trả về Telegram]
```

### Skill: `finance-expense`
**Triggers:**
- "thêm chi tiêu ...", "ghi lại ...", "tôi vừa xài ..."
- "chi [số tiền] [mô tả]"
- User gửi ảnh → tự động route sang `finance-ocr`

**Gọi API:** `POST /api/v1/ingestion/manual` hoặc `POST /api/v1/ingestion/ocr`

### Skill: `finance-ocr`
**Triggers:** User gửi file ảnh bất kỳ

**Quan trọng — Model override:**
```json
// openclaw.json config cho skill này
"finance-ocr": {
  "imageModel": "claude-opus-4-6"
}
```
Vì DeepSeek không có Vision, skill này phải dùng Claude.

**Flow:**
```
Nhận ảnh → gọi POST /api/v1/ingestion/ocr (multipart/form-data)
→ Backend gọi Claude Vision → trả về JSON
→ Skill hỏi confirm qua Telegram
→ User confirm → gọi POST /api/v1/expenses
```

### Skill: `finance-report`
**Triggers:**
- "báo cáo tháng này / tháng trước"
- "tôi xài bao nhiêu tiền [category]?"
- "so sánh chi tiêu"
- "tỷ lệ tiết kiệm của tôi"

**Gọi API:** `GET /api/v1/reports/monthly?month=YYYY-MM`

### Skill: `finance-goals`
**Triggers:**
- "tôi muốn tiết kiệm X để Y trong Z tháng"
- "cập nhật tiến độ mục tiêu"
- "thu nhập tháng này là X"
- "tiến độ các mục tiêu?"

**Gọi API:** `POST/PUT /api/v1/goals`, `POST /api/v1/users/income`

### Skill: `finance-market`
**Triggers:**
- "thị trường hôm nay thế nào?"
- "VN-Index đang ở đâu?"
- "nên đầu tư gì?"
- "phân tích tài chính của tôi"

**Gọi API:** `GET /api/v1/market/snapshot`, `POST /api/v1/market/advice`

---

## 6. Service Layer — Business Logic

### `expense_service.py`

**`categorize_expense(merchant, description, amount) → category`**
- Check `llm_cache` trước (cache 30 ngày cho cùng merchant)
- Nếu cache miss → gọi DeepSeek với prompt phân loại
- Lưu kết quả vào cache
- Categories: `food_drink | transport | shopping | health | entertainment | utilities | investment | savings | other | needs_review`

**`check_budget_alert(user_id, category, new_amount) → alert | None`**
- Tính tổng category tháng hiện tại sau khi thêm expense mới
- So sánh với `monthly_income * budget_ratio[category]`
- Default budget ratios: food_drink 30%, transport 15%, shopping 20%, health 10%, entertainment 10%, utilities 10%, savings 5%
- Nếu > 80% ngưỡng → return cảnh báo text

**`dedup_check(gmail_message_id) → bool`**
- Check `expenses.gmail_message_id` trước khi insert từ Gmail

### `gmail_service.py`

**`sync_new_receipts(user_id) → List[Expense]`**
- Query Gmail API: `newer_than:30m label:inbox`
- Filter theo `RECEIPT_KEYWORDS` list
- Với mỗi email match:
  - Extract plain text từ HTML body
  - Gọi `llm_service.parse_receipt_email(text)`
  - Dedup check
  - Insert vào DB
  - Add label `finance-processed` trên Gmail
- Return danh sách expenses đã tạo

**`RECEIPT_KEYWORDS`** (bổ sung thêm khi cần):
```python
RECEIPT_KEYWORDS = [
    # Senders (domain)
    "shopee.vn", "lazada.vn", "grab.com", "gojek.com",
    "tiki.vn", "momo.vn", "vnpay.vn", "zalopay.vn",
    # Subject keywords
    "hóa đơn", "receipt", "invoice", "order confirmation",
    "đơn hàng", "thanh toán thành công", "giao dịch thành công",
    "payment confirmation", "your order"
]
```

### `ocr_service.py`

**`parse_receipt_image(image_bytes, mime_type) → dict`**
- Gọi Claude API (Anthropic) với Vision
- Prompt:
  ```
  Đây là hóa đơn/receipt. Hãy trích xuất thông tin và trả về JSON hợp lệ:
  {
    "total_amount": <số thực, chỉ số không có đơn vị>,
    "currency": <"VND" hoặc currency khác>,
    "merchant_name": <tên nơi mua>,
    "date": <"YYYY-MM-DD" hoặc null nếu không rõ>,
    "items": [{"name": <tên>, "price": <giá>}],
    "category_suggestion": <một trong: food_drink|transport|shopping|health|entertainment|utilities|other>,
    "confidence": <"high"|"medium"|"low">,
    "error": <null hoặc "not_a_receipt" nếu không phải hóa đơn>
  }
  Chỉ trả về JSON, không có text khác.
  ```
- Validate JSON response
- Nếu `confidence == "low"` → set `needs_review = true`

### `llm_service.py`

**LLM Routing Rules:**
```python
# Dùng Claude cho:
USE_CLAUDE = ["ocr", "complex_analysis"]

# Dùng DeepSeek cho tất cả còn lại:
USE_DEEPSEEK = ["categorize", "parse_email", "report_text",
                "investment_advice", "intent_detection"]
```

**`call_llm(prompt, task_type, use_cache=True) → str`**
- Check cache nếu `use_cache=True`
- Route đến đúng model
- Log token usage cho cost tracking
- Raise `LLMError` nếu fail, không swallow exception

### `market_service.py`

**`fetch_daily_snapshot() → List[MarketSnapshot]`**

Nguồn dữ liệu:
```python
# VN-Index và VN30 — dùng vnstock
import vnstock
indices = ['VNINDEX', 'VN30', 'HNXINDEX']

# Chứng chỉ quỹ — scrape cafef.vn
# Target: DCDS, VESAF, VFMVF1, VCBF-BCF, SSIBF

# Không scrape BĐS real-time (quá phức tạp và ít thay đổi)
# Thay bằng: user tự nhập giá BĐS tham khảo qua Telegram
```

**`generate_investment_advice(user_id) → str`**

Context gửi cho DeepSeek:
```python
context = {
    "market": {
        "vnindex_current": ...,
        "vnindex_change_1m_pct": ...,
        "top_funds": [...],  # NAV + thay đổi
    },
    "user": {
        "monthly_income": ...,
        "monthly_expense_avg_3m": ...,
        "cash_available": ...,  # income - expense tháng này
        "active_goals": [...],
        "existing_investments": ...  # từ expenses category=investment
    }
}
```

Prompt yêu cầu output gồm:
1. Nhận định ngắn thị trường (2-3 câu)
2. Gợi ý cụ thể có lý do (1-2 gợi ý)
3. Disclaimer bắt buộc

---

## 7. Jobs (Scheduled Tasks)

### Cron Schedule
```python
# Dùng APScheduler trong FastAPI (không dùng crontab hệ thống)
# Phase 0: chạy trong cùng process FastAPI
# Phase 1+: tách thành Celery workers

SCHEDULES = {
    "gmail_sync":      "*/30 * * * *",   # Mỗi 30 phút
    "market_snapshot": "0 8 * * *",      # 8:00 sáng hàng ngày
    "monthly_report":  "0 9 1 * *",      # 9:00 sáng ngày 1 hàng tháng
}
```

### `gmail_poller.py`
```
1. Lấy tất cả active users có Gmail connected
2. Với mỗi user: gọi gmail_service.sync_new_receipts()
3. Nếu có expenses mới: push Telegram notification
4. Log kết quả
```

### `market_poller.py`
```
1. Gọi market_service.fetch_daily_snapshot()
2. Lưu vào market_snapshots table
3. Check nếu có signal đặc biệt (VN-Index thay đổi > 3%)
   → Push alert cho tất cả users có market_intel enabled
```

### `monthly_report.py`
```
1. Với mỗi active user:
   a. Gọi report_service.generate_monthly_report(user_id, prev_month)
   b. Lưu vào monthly_reports table
   c. Sync lên Notion (notion_sync.py)
   d. Push full report qua Telegram
```

---

## 8. Notion Sync (Secondary — Dashboard only)

**Đây là sync 1 chiều: PostgreSQL → Notion**
Không bao giờ đọc từ Notion vào PostgreSQL.

### Sync trigger
- Sau mỗi lần tạo/update expense
- Sau khi generate monthly report
- Có thể gọi manual qua API: `POST /api/v1/sync/notion`

### 5 Notion Databases cần tạo thủ công

Owner phải tạo các database này trong Notion và điền IDs vào `.env`:

```
NOTION_EXPENSES_DB_ID=
NOTION_GOALS_DB_ID=
NOTION_REPORTS_DB_ID=
NOTION_MARKET_DB_ID=
NOTION_INVESTMENT_LOG_DB_ID=
```

### Schema Notion `Expenses` DB
```
Date (Date)
Amount (Number — format: Vietnamese Dong)
Merchant (Text)
Category (Select)
Source (Select)
Month (Text)
Note (Text)
Needs Review (Checkbox)
```

---

## 9. Environment Variables

```bash
# .env.example — copy thành .env và điền giá trị thật

# === Backend ===
ENVIRONMENT=development          # development | production
PORT=8000
INTERNAL_API_KEY=                # Random string dài, dùng cho OpenClaw Skills gọi API

# === Database ===
DATABASE_URL=postgresql+asyncpg://finance:password@localhost:5432/finance_db
# Phase 1+: đổi thành connection string cloud DB

# === LLM APIs ===
DEEPSEEK_API_KEY=                # Primary LLM
DEEPSEEK_BASE_URL=https://api.deepseek.com
ANTHROPIC_API_KEY=               # Chỉ dùng cho OCR (Claude Vision)

# === Gmail OAuth2 ===
GMAIL_CLIENT_ID=
GMAIL_CLIENT_SECRET=
GMAIL_REDIRECT_URI=http://localhost:8000/auth/gmail/callback
# Refresh token lưu per-user trong DB, không phải env

# === Notion ===
NOTION_API_KEY=
NOTION_EXPENSES_DB_ID=
NOTION_GOALS_DB_ID=
NOTION_REPORTS_DB_ID=
NOTION_MARKET_DB_ID=
NOTION_INVESTMENT_LOG_DB_ID=

# === Telegram (để backend push notifications) ===
TELEGRAM_BOT_TOKEN=
OWNER_TELEGRAM_ID=               # Telegram user ID của owner

# === OpenClaw Skills ===
FINANCE_API_URL=http://localhost:8000/api/v1
FINANCE_API_KEY=                 # = INTERNAL_API_KEY ở trên
```

---

## 10. docker-compose.yml

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:16-alpine
    container_name: finance-postgres
    environment:
      POSTGRES_USER: finance
      POSTGRES_PASSWORD: password      # Đổi trong production
      POSTGRES_DB: finance_db
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U finance -d finance_db"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: finance-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    restart: unless-stopped
    # Phase 0: Redis optional, enable khi cần cache

volumes:
  postgres_data:
  redis_data:
```

---

## 11. Dependencies (requirements.txt)

```
# Web framework
fastapi>=0.110.0
uvicorn[standard]>=0.27.0
python-multipart>=0.0.9        # File upload

# Database
sqlalchemy[asyncio]>=2.0.0
asyncpg>=0.29.0                # Async PostgreSQL driver
alembic>=1.13.0                # Database migrations

# Scheduling
apscheduler>=3.10.0

# LLM
anthropic>=0.25.0              # Claude Vision
openai>=1.0.0                  # DeepSeek dùng OpenAI-compatible SDK

# Gmail
google-auth-oauthlib>=1.0.0
google-auth-httplib2>=0.2.0
google-api-python-client>=2.120.0

# Notion
notion-client>=2.2.0

# Market data
vnstock>=0.3.0
requests>=2.31.0
beautifulsoup4>=4.12.0
lxml>=5.0.0

# Utils
python-dotenv>=1.0.0
pydantic-settings>=2.0.0
python-dateutil>=2.8.0
Pillow>=10.0.0                 # Image processing trước khi gửi OCR
httpx>=0.27.0                  # Async HTTP client

# Dev only
pytest>=8.0.0
pytest-asyncio>=0.23.0
```

---

## 12. Build Order — Phase 0

Implement **theo đúng thứ tự này**. Không skip bước. Mỗi bước phải test xong trước khi sang bước tiếp.

### Bước 1: Infrastructure
```
- [ ] Tạo cấu trúc thư mục dự án (xem mục 2)
- [ ] docker-compose.yml — chạy PostgreSQL + Redis
- [ ] .env từ .env.example
- [ ] Verify: docker-compose up -d && docker ps
```

### Bước 2: Database Foundation
```
- [ ] backend/database.py — SQLAlchemy async engine
- [ ] backend/models/*.py — tất cả ORM models (mục 3)
- [ ] Alembic init + migration đầu tiên
- [ ] Verify: alembic upgrade head && kiểm tra tables trong psql
```

### Bước 3: FastAPI Skeleton
```
- [ ] backend/config.py — load env vars
- [ ] backend/main.py — app init, health check endpoint
- [ ] Verify: uvicorn main:app --reload → GET /health trả về 200
```

### Bước 4: Expense CRUD
```
- [ ] backend/schemas/expense.py
- [ ] backend/services/expense_service.py (CRUD, không có LLM trước)
- [ ] backend/routers/expenses.py
- [ ] Verify: POST /api/v1/expenses với data test → lưu DB → GET lại được
```

### Bước 5: Goals CRUD
```
- [ ] backend/schemas/goal.py
- [ ] backend/services/goal_service.py
- [ ] backend/routers/goals.py
- [ ] Verify: CRUD goals hoạt động
```

### Bước 6: LLM Service + Categorization
```
- [ ] backend/services/llm_service.py (DeepSeek + Claude routing)
- [ ] Thêm categorize_expense() vào expense_service.py
- [ ] Thêm llm_cache table và caching logic
- [ ] Verify: POST expense với merchant → category tự động được assign
```

### Bước 7: OpenClaw Skills — Expense + Goals
```
- [ ] openclaw-skills/finance-expense/SKILL.md + expense_cli.py
- [ ] openclaw-skills/finance-goals/SKILL.md + goals_cli.py
- [ ] Cài vào OpenClaw: copy vào ~/.openclaw/skills/
- [ ] Verify: nhắn Telegram "thêm chi tiêu 150k ăn trưa" → lưu DB
```

### Bước 8: OCR Pipeline
```
- [ ] backend/services/ocr_service.py (Claude Vision)
- [ ] backend/routers/ingestion.py — POST /ingestion/ocr endpoint
- [ ] openclaw-skills/finance-ocr/SKILL.md + ocr_cli.py
- [ ] Verify: gửi ảnh hóa đơn qua Telegram → parse đúng → confirm → lưu DB
```

### Bước 9: Gmail Integration
```
- [ ] Tạo Google Cloud project + enable Gmail API + OAuth consent
- [ ] backend/services/gmail_service.py
- [ ] backend/routers/ingestion.py — Gmail OAuth flow + sync endpoint
- [ ] backend/jobs/gmail_poller.py
- [ ] Verify: chạy sync thủ công → email receipts trong inbox được parse
```

### Bước 10: Report Generation
```
- [ ] backend/services/report_service.py
- [ ] backend/routers/reports.py
- [ ] openclaw-skills/finance-report/SKILL.md + report_cli.py
- [ ] Verify: nhắn "báo cáo tháng này" → nhận report đúng format
```

### Bước 11: Notion Sync
```
- [ ] Tạo 5 Notion databases thủ công, lấy IDs
- [ ] backend/services/notion_sync.py
- [ ] Integrate vào expense_service (trigger sau mỗi save)
- [ ] Verify: thêm expense → tự động xuất hiện trong Notion
```

### Bước 12: Market Intelligence
```
- [ ] backend/services/market_service.py (vnstock + cafef scraper)
- [ ] backend/jobs/market_poller.py
- [ ] backend/routers/market.py
- [ ] openclaw-skills/finance-market/SKILL.md + market_cli.py
- [ ] Verify: nhắn "thị trường hôm nay?" → nhận snapshot + analysis
```

### Bước 13: Monthly Report Job
```
- [ ] backend/jobs/monthly_report.py
- [ ] Integrate APScheduler vào FastAPI startup
- [ ] Test với tháng hiện tại (force generate)
- [ ] Verify: report tự động gửi Telegram cuối tháng
```

---

## 13. Coding Conventions

### Python
- Dùng **async/await** cho tất cả I/O operations (DB, API calls, file)
- Type hints bắt buộc cho tất cả function signatures
- Dùng Pydantic models cho tất cả data validation
- Exception handling: raise exception cụ thể, không swallow silently
- Logging: dùng Python `logging` module, không dùng `print()`

### API Design
- Response format thống nhất:
```python
# Success
{"data": {...}, "error": null}

# Error
{"data": null, "error": {"code": "EXPENSE_NOT_FOUND", "message": "..."}}
```
- HTTP status codes đúng chuẩn: 200, 201, 400, 401, 404, 422, 500
- Tất cả endpoints đều nhận `user_id` từ API key lookup (Phase 0) hoặc JWT (Phase 1+)

### Security
- **KHÔNG BAO GIỜ** hardcode credentials trong code
- **KHÔNG BAO GIỜ** commit file `.env`
- Tất cả secrets đọc từ environment variables qua `config.py`
- SQL queries: luôn dùng SQLAlchemy ORM hoặc parameterized queries — không string concat

### Testing
- Mỗi service function phải có ít nhất 1 unit test
- Integration tests cho các API endpoints chính
- Test file đặt trong `backend/tests/`

---

## 14. Scale Roadmap — Khi nào làm gì

### Phase 0 → Phase 1 (khi có ~100 users beta)
```
- [ ] Deploy FastAPI lên VPS (DigitalOcean / Hetzner ~$20/tháng)
- [ ] PostgreSQL lên managed DB (Supabase free tier → paid)
- [ ] Thêm JWT authentication thay API key đơn
- [ ] Telegram Bot public — users tự đăng ký
- [ ] Gmail OAuth per-user (không dùng OAuth của owner)
- [ ] Basic rate limiting
```

### Phase 1 → Phase 2 (khi có ~1,000 users)
```
- [ ] Tách jobs (gmail_poller, market_poller) ra Celery workers riêng
- [ ] Redis cache cho LLM responses và session
- [ ] Web dashboard (Next.js) thay Notion
- [ ] Subscription model (Stripe)
- [ ] Monitoring: Sentry + Grafana
```

### Phase 2 → Phase 3 (khi có ~10,000 users)
```
- [ ] Kubernetes deployment
- [ ] Tách microservices: Ingestion / Core / Intelligence / Notification
- [ ] Read replicas cho PostgreSQL
- [ ] CDN cho static assets
- [ ] Multi-region (Singapore primary, backup HCM)
```

### Phase 3 → Phase 4 (khi có ~100,000+ users)
```
- [ ] Horizontal auto-scaling
- [ ] Global load balancing
- [ ] LLM cost optimization: fine-tuned model cho categorization
- [ ] Real-time features (WebSocket)
- [ ] Advanced analytics pipeline (ClickHouse)
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

**LLM cost optimization là ưu tiên từ Phase 1:**
- Cache category lookup: giảm 70% LLM calls
- Dùng DeepSeek thay Claude cho mọi thứ trừ Vision: tiết kiệm ~80%
- Batch processing Gmail: 1 LLM call cho nhiều emails thay vì 1 call/email

---

*Document version: 1.0*
*Cập nhật khi có thay đổi kiến trúc quan trọng*
*Khi implement, comment vào đây nếu phát hiện design cần điều chỉnh*
