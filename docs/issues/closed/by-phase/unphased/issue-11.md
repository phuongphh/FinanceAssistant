# Issue #11

[Feature] Automated Gmail Expense Sync — Hourly Auto-Sync & Manual Trigger

## Overview
Implement an automated expense synchronization system that reads invoices/receipts from Gmail and writes expense records to the database. The system supports two modes:
1. **Auto-sync** — runs every hour automatically
2. **Manual trigger** — user can request a sync via natural language command

---

## Requirements

### 1. Hourly Auto-Sync (Background Job)
- Run a background scheduler every **60 minutes**
- Scan Gmail for **new emails since last sync timestamp** (`last_scan_at` per user)
- Detect and parse invoices/receipts from supported senders (see Parsing Rules below)
- Extract expense data from each email:
  - `amount` (VND)
  - `merchant` / `source`
  - `category` (auto-classified)
  - `transaction_date`
  - `email_id` (để tránh duplicate)
- Write extracted expenses to DB (`expenses` table)
- Update `last_scan_at` timestamp after each successful scan
- **Deduplication:** Check `email_id` before inserting — never write the same email twice

---

### 2. Manual Trigger via Natural Language
When user sends a message like:
> *"hãy kiểm tra trong mail xem có chi phí gì mới"*
> *"sync gmail đi"*
> *"có hoá đơn mới không?"*

The bot will:
1. **Scan Gmail** from last sync timestamp to now
2. **Compare** newly found expenses vs. already-recorded expenses in DB
3. **Identify gaps** — any expenses in Gmail not yet in DB
4. **Sync missing records** to DB automatically
5. **Report back** to user with a summary:
   - Số email đã quét
   - Số chi phí mới tìm thấy
   - Danh sách chi phí vừa được sync (merchant, amount, date)
   - Thông báo nếu không có gì mới

---

### 3. Data Model — `expenses` table
```sql
CREATE TABLE IF NOT EXISTS expenses (
  id               UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          UUID          NOT NULL REFERENCES user_profiles(id),
  amount           DECIMAL(15,0) NOT NULL,         -- VND
  merchant         VARCHAR(100),
  category         VARCHAR(50),                    -- transport|food|travel|banking|llm|cloud|other
  transaction_date DATE          NOT NULL,
  source           VARCHAR(20)   DEFAULT 'gmail',  -- 'gmail' | 'ocr' | 'manual'
  email_id         VARCHAR(255)  UNIQUE,           -- Gmail message ID, NULL nếu không từ gmail
  raw_content      TEXT,                           -- raw email snippet để debug
  created_at       TIMESTAMP     DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_expenses_user_id ON expenses(user_id);
CREATE INDEX IF NOT EXISTS idx_expenses_transaction_date ON expenses(transaction_date);
CREATE INDEX IF NOT EXISTS idx_expenses_email_id ON expenses(email_id);
```

---

### 4. Gmail Parsing Rules

| Sender | Parse target | Key fields | Category |
|--------|-------------|------------|----------|
| UOB Bank | Transaction alert email | Amount, merchant, date | `banking` |
| Grab | Receipt email | Amount, trip/order type, date | `transport` / `food` |
| Xanh SM | Receipt email | Amount, date | `transport` |
| Traveloka | Booking confirmation | Amount, destination, date | `travel` |
| Anthropic (Claude) | Invoice / subscription email | Amount, plan, date | `llm` |
| DeepSeek | Invoice / credit purchase email | Amount, credits, date | `llm` |
| OpenAI | Invoice / credit purchase email | Amount, plan/credits, date | `llm` |
| Google Cloud | Billing statement / invoice | Amount, services, date | `cloud` |
| AWS (Amazon Web Services) | Billing statement / invoice | Amount, services, date | `cloud` |

**Category list:**
- `transport` — Grab, Xanh SM
- `food` — Grab Food
- `travel` — Traveloka
- `banking` — UOB và các ngân hàng
- `llm` — Claude, DeepSeek, OpenAI (AI/LLM services)
- `cloud` — Google Cloud, AWS (cloud infrastructure)
- `other` — không phân loại được

**Parser rules:**
- Parser phải **fail gracefully** — nếu không parse được thì log lại, không crash
- Hỗ trợ cả **email HTML** và **plain text**
- Với LLM/Cloud invoices: convert USD → VND theo tỷ giá tại thời điểm nhận email (hoặc ghi nguyên USD nếu chưa có tỷ giá)

---

### 5. Technical Requirements
- Scheduler: APScheduler hoặc Celery Beat (tùy stack hiện tại)
- Gmail API: OAuth2, scope `gmail.readonly`
- Sync chạy **per user** — mỗi user có `last_scan_at` riêng
- Background job phải **idempotent** — chạy lại không tạo duplicate
- Log đầy đủ: số email scanned, parsed, inserted, skipped

---

## Acceptance Criteria
- [ ] Hourly background job chạy đúng giờ và tự động sync Gmail
- [ ] `last_scan_at` được cập nhật sau mỗi lần sync thành công
- [ ] Deduplication hoạt động — không có expense bị ghi 2 lần
- [ ] Manual trigger nhận diện đúng intent từ natural language
- [ ] Manual trigger báo cáo rõ ràng: số email quét, số chi phí mới sync
- [ ] Parser xử lý đúng email từ: UOB, Grab, Xanh SM, Traveloka, Claude, DeepSeek, OpenAI, Google Cloud, AWS
- [ ] LLM/Cloud invoices được phân loại đúng category (`llm` / `cloud`)
- [ ] Parse fail → log lỗi, không crash bot
- [ ] Expenses table được tạo đúng schema với indexes
- [ ] Unit tests cho Gmail parser (mỗi sender có ít nhất 1 test case)
