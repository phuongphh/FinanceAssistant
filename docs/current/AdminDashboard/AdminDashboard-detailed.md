# Phase 3.6: Admin Observability Layer — Implementation Guide

> **Status**: Design complete · Ready for implementation
> **Owner**: Phuong
> **Target start**: Soft launch tuần 5
> **Estimated effort**: 3 sprints (~3 tuần)
> **Dependencies**: Phase 3A (Wealth Foundation) đã ship, Phase 3.5 (Intent Layer) đã design

---

## Mục lục

1. [Executive Summary](#1-executive-summary)
2. [Mục tiêu & Vision](#2-mục-tiêu--vision)
3. [Phạm vi (In Scope / Out of Scope)](#3-phạm-vi)
4. [User Personas & Use Cases](#4-user-personas--use-cases)
5. [Architecture](#5-architecture)
6. [Metrics & KPIs](#6-metrics--kpis)
7. [Backend API Specifications](#7-backend-api-specifications)
8. [Database Schema & Queries](#8-database-schema--queries)
9. [Frontend Architecture](#9-frontend-architecture)
10. [UI/UX Specifications](#10-uiux-specifications)
11. [Security](#11-security)
12. [Deployment](#12-deployment)
13. [Performance & Scalability](#13-performance--scalability)
14. [Roadmap & Future](#14-roadmap--future)
15. [Architecture Decision Records](#15-architecture-decision-records)
16. [Open Questions](#16-open-questions)

---

## 1. Executive Summary

Phase 3.6 xây dựng **Admin Observability Layer** — một dashboard web nội bộ giúp Phuong và team monitor sức khỏe sản phẩm Bé Tiền trong giai đoạn soft launch. Dashboard trả lời 3 câu hỏi cốt lõi:

1. **Có ai dùng không, và họ có quay lại không?** — Acquisition + Retention
2. **Họ dùng cái gì, có bí ở đâu không?** — Engagement + Friction
3. **Bé Tiền đang đốt bao nhiêu chi phí mỗi user?** — Unit economics

Dashboard cũng đặt nền móng cho **License Management** (Phase 5), với placeholder UI và data model sẵn sàng để activate khi launch paid tier.

**Key deliverables:**
- 1 React SPA (Vite + Tailwind + Recharts) deploy tại `admin.betien.vn`
- ~12 FastAPI endpoints dưới namespace `/api/admin/*`
- 1 admin auth flow (JWT-based)
- Audit log model + service
- License data model (foundation only, chưa activate)

---

## 2. Mục tiêu & Vision

### Mục tiêu kinh doanh

- **Đo lường được sự thành công của soft launch**: Phuong cần data thực tế thay vì cảm nhận để quyết định launch full hay tiếp tục iterate.
- **Phát hiện sớm vấn đề product**: Retention drop, asset coverage thấp, intent classification fail rate cao — phát hiện trước khi mất user.
- **Kiểm soát chi phí LLM**: Đảm bảo target 75% rule-based (Phase 3.5) đang hoạt động đúng kỳ vọng.
- **Chuẩn bị nền móng monetization**: Khi chuyển sang paid tier, đã có sẵn license management framework.

### Vision

Trong 12 tháng tới, dashboard này phát triển thành **Bé Tiền Operations Console** — không chỉ monitor mà còn cho phép admin:
- Quản lý license, refund, upgrade
- A/B test các thay đổi UX
- Customer support (xem lịch sử conversation, trợ giúp user)
- Tài chính (MRR, ARR, churn, LTV/CAC)

Phase 3.6 chỉ scope phần monitoring & user list — các phần khác là phase sau.

---

## 3. Phạm vi

### In Scope (v1.0)

- ✅ Admin authentication (JWT, single admin role)
- ✅ Overview KPI cards (12 chỉ số cốt lõi)
- ✅ Time-series charts: User growth, DAU, feature clicks
- ✅ Distribution charts: Intent breakdown, user tier
- ✅ Retention cohort table
- ✅ User directory với search/filter/sort
- ✅ User detail view (modal hoặc page)
- ✅ Manual refresh & 30-day date range
- ✅ Responsive trên mobile (≥375px)
- ✅ Audit log cho mọi admin action
- ✅ License data model (chưa có UI quản lý)

### Out of Scope (defer sau)

- ❌ Multi-admin với phân quyền (RBAC) — chỉ 1 admin role trong v1.0
- ❌ Real-time updates (WebSocket) — manual refresh đủ cho soft launch
- ❌ Customizable date ranges (chỉ preset 7/14/30/90 ngày)
- ❌ Export to CSV/Excel — defer sang v1.1
- ❌ Email/Slack alerts khi metric bất thường — defer sang v1.2
- ❌ A/B testing framework — defer sang v2.0
- ❌ License management UI (chỉ có data model)
- ❌ Customer support conversation viewer

---

## 4. User Personas & Use Cases

### Persona chính: Phuong (Founder/Admin)

**Goals**: Monitor sức khỏe sản phẩm hằng ngày, phát hiện sớm vấn đề, ra quyết định product dựa trên data.

**Pain points hiện tại**:
- Không biết user đang dùng feature nào nhiều nhất → không biết prioritize gì.
- Không biết retention thực tế → không biết product có sticky không.
- Không biết LLM cost per user → không biết unit economics khi scale.

### Use cases ưu tiên

| # | Use case | Tần suất | Importance |
|---|----------|---------|------------|
| UC1 | Mở dashboard buổi sáng xem có user mới và DAU hôm qua | Hằng ngày | Critical |
| UC2 | Kiểm tra LLM cost tuần này có vượt budget không | Tuần | Critical |
| UC3 | Tìm 1 user cụ thể để xem tình trạng (cho support) | Ad-hoc | High |
| UC4 | Xem cohort retention để đánh giá impact của feature mới | Tuần | High |
| UC5 | Identify users at-risk (lâu không active) để outreach | Tuần | Medium |
| UC6 | Báo cáo metrics cho investor/advisor | Tháng | Medium |

---

## 5. Architecture

### 5.1. Tổng quan kiến trúc

```
┌─────────────────────────────────────────────────────────┐
│                     BROWSER (Admin)                      │
│        React SPA · Vite · Tailwind · Recharts            │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTPS + JWT
                       ▼
┌─────────────────────────────────────────────────────────┐
│                 CADDY (Reverse Proxy)                    │
│         SSL termination · Static files · Rate limit      │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│            FastAPI · /api/admin/* router                 │
│   Auth middleware · Audit log · Business logic           │
└──────────┬──────────────────────────────────────────────┘
           │                                  │
           ▼                                  ▼
┌──────────────────────┐         ┌──────────────────────┐
│   PostgreSQL         │         │   Redis              │
│   - users            │         │   - session cache    │
│   - messages         │         │   - rate limit       │
│   - llm_calls        │         │   - aggregate cache  │
│   - feature_events   │         └──────────────────────┘
│   - assets           │
│   - admin_users      │  ← NEW
│   - admin_audit_log  │  ← NEW
│   - licenses         │  ← NEW (data only)
└──────────────────────┘
```

### 5.2. Component layout

```
be_tien_backend/
├── app/
│   ├── api/
│   │   ├── admin/                    ← NEW (toàn bộ Phase 3.6)
│   │   │   ├── __init__.py
│   │   │   ├── deps.py               ← Auth dependency
│   │   │   ├── auth.py               ← Login/logout/me
│   │   │   ├── stats.py              ← Overview KPI
│   │   │   ├── charts.py             ← Chart data endpoints
│   │   │   ├── users.py              ← User CRUD/list/detail
│   │   │   ├── audit.py              ← Audit log query
│   │   │   └── licenses.py           ← License placeholder
│   │   └── ...
│   ├── models/
│   │   ├── admin_user.py             ← NEW
│   │   ├── admin_audit_log.py        ← NEW
│   │   └── license.py                ← NEW
│   ├── services/
│   │   ├── admin_metrics.py          ← NEW — business logic
│   │   ├── admin_audit.py            ← NEW
│   │   └── cohort_analysis.py        ← NEW
│   └── static/
│       └── admin/                    ← NEW (build output từ Vite)
│           ├── index.html
│           └── assets/
│
└── betien-admin/                     ← NEW (separate Vite project)
    ├── src/
    │   ├── App.jsx
    │   ├── api/                      ← API client (fetch wrapper)
    │   ├── components/
    │   │   ├── KPICard.jsx
    │   │   ├── ChartCard.jsx
    │   │   ├── UserTable.jsx
    │   │   ├── CohortTable.jsx
    │   │   └── ...
    │   ├── pages/
    │   │   ├── Login.jsx
    │   │   └── Dashboard.jsx
    │   └── hooks/
    │       └── useAuth.jsx
    └── package.json
```

### 5.3. Tech stack

| Layer | Technology | Lý do |
|-------|-----------|------|
| Frontend framework | React 18 + Vite | Build nhanh, dev experience tốt, ecosystem mạnh |
| Styling | Tailwind CSS 3.4 | Đồng nhất với hệ design tokens, không cần CSS riêng |
| Charts | Recharts 2.12 | Declarative, responsive sẵn, đủ chart cho v1.0 |
| Icons | Lucide React | Bộ icon clean, đồng bộ thiết kế editorial |
| Fonts | Fraunces + Geist + JetBrains Mono | Display serif cho hero numbers, sans clean cho UI, mono cho data |
| HTTP client | Fetch API native | Đơn giản, không cần axios cho scope này |
| State | React useState/useReducer | Đủ cho scope, không cần Redux/Zustand |
| Backend | FastAPI (existing) | Tái dùng codebase, share auth pattern |
| DB | PostgreSQL (existing) | Tái dùng |
| Cache | Redis (existing) | Cache aggregate cho expensive queries |
| Reverse proxy | Caddy | Auto-SSL, đơn giản |

### 5.4. Multi-tenancy considerations

Theo principle "Multi-tenancy from day one" của Bé Tiền:

- Mọi endpoint analytics MẶC ĐỊNH scope theo `tenant_id` của user đang login (kể cả admin).
- Trong v1.0, chỉ có 1 tenant (Phuong), nên `tenant_id` là single value.
- Admin role có 2 mức trong tương lai: `tenant_admin` (chỉ xem data tenant mình) và `super_admin` (xem toàn bộ). V1.0 chỉ implement `super_admin`.
- Query SQL phải có WHERE `tenant_id = :current_tenant` ở mọi nơi (trừ super_admin endpoint).

---

## 6. Metrics & KPIs

### 6.1. North Star metric

**Weekly Active Users with ≥1 asset tracked (WAU-Activated)** — số user vừa active trong tuần vừa đã nhập ít nhất 1 tài sản. Đây là chỉ số gần nhất với value prop "Personal CFO" của Bé Tiền.

### 6.2. Acquisition

| Metric | Định nghĩa | Công thức | Cập nhật |
|--------|-----------|----------|---------|
| Total Users | Tổng user đã từng đăng ký | `COUNT(users)` | Daily |
| New Users (D, W, M) | User mới trong period | `COUNT(users WHERE created_at >= period_start)` | Daily |
| Cumulative User Growth | Tăng trưởng tổng | Running count theo ngày | Daily |
| Activation Rate | % user nhập ≥1 asset trong 7 ngày đầu | `activated_users / total_signups_30d` | Daily |

### 6.3. Engagement

| Metric | Định nghĩa | Target | Cập nhật |
|--------|-----------|-------|---------|
| DAU | Daily Active Users (gửi ≥1 message) | — | Real-time |
| WAU | Weekly Active Users | — | Daily |
| MAU | Monthly Active Users | — | Daily |
| **Stickiness** | DAU/MAU × 100 | ≥20% (top 10% SaaS: 50%+) | Daily |
| Messages per active user / day | Trung bình message/user/ngày | — | Daily |
| Briefing open rate | % user mở morning briefing | ≥60% | Daily |
| Asset coverage | % user có ≥1 asset | ≥70% | Daily |

### 6.4. Retention

| Metric | Định nghĩa | Target |
|--------|-----------|-------|
| D1 retention | % user active vào ngày D+1 sau đăng ký | ≥40% |
| D7 retention | % user active vào ngày D+7 | ≥25% |
| D30 retention | % user active vào ngày D+30 | ≥15% |
| Weekly cohort retention | Matrix theo tuần đăng ký × tuần active | — |

### 6.5. Bé Tiền-specific

| Metric | Định nghĩa | Tại sao quan trọng |
|--------|-----------|------------------|
| Time-to-first-asset | Khoảng cách từ signup → nhập asset đầu tiên | Predictor của retention |
| Asset diversity | Số loại asset trung bình/user (stock, gold, crypto…) | Indicator của tier Mass Affluent+ |
| Morning briefing CTR | % user click action sau khi đọc briefing | Đo value của briefing |
| Storytelling expense rate | % expense 200k-2M VND được capture qua storytelling | Đo UX flow Phase 3A |
| Tier distribution | Phân bố theo Ladder (Starter/Young Pro/Mass Affluent/HNW) | Xác định fit thị trường |

**Tier classification thresholds** (xác nhận với Phuong 2026-05-13, dựa vào tổng giá trị asset của user):

| Tier | Total asset value (VND) |
|------|------------------------|
| Starter | < 100M |
| Young Pro | 100M – 500M |
| Mass Affluent | 500M – 5B |
| HNW | ≥ 5B |

### 6.6. Cost & Unit Economics

| Metric | Định nghĩa | Target |
|--------|-----------|-------|
| **Total LLM cost (month)** | Tổng chi phí LLM tháng hiện tại (USD) | Giữ <$X/MAU |
| Avg cost per active user | Total cost / MAU | <$0.20 |
| Cost per message | Total cost / total messages | — |
| **Rule-based ratio** | % message resolved bằng rule (Phase 3.5) | ≥75% |
| LLM classifier ratio | % message qua LLM classifier | ≤22% |
| Clarification ratio | % message cần clarify | ≤5% |
| Cost breakdown by intent type | Phân bố cost theo loại intent | — |

### 6.7. Product health

| Metric | Định nghĩa | Alert threshold |
|--------|-----------|----------------|
| Error rate | % message bị error (5xx, timeout) | >3% |
| Avg response latency | Latency trung bình của bot response | >3s |
| P95 latency | 95th percentile latency | >8s |
| Failed asset captures | Số lần Vision/OCR fail | >5% |
| At-risk user count | User đã 3-7 ngày không active | — |
| Dormant user count | User >7 ngày không active | — |

---

## 7. Backend API Specifications

### 7.1. Conventions

- **Base URL**: `/api/admin/*`
- **Auth**: Header `Authorization: Bearer <JWT>`
- **Response format**: JSON
- **Error format**: `{ "error": { "code": "...", "message": "..." } }`
- **Pagination**: `?limit=50&offset=0`, response có `total`, `limit`, `offset`
- **Date params**: ISO 8601 (`2026-05-13`)
- **Timezone**: Asia/Ho_Chi_Minh (UTC+7), backend lưu UTC, convert khi response

### 7.2. Authentication endpoints

#### `POST /api/admin/auth/login`

Request:
```json
{ "email": "phuong@betien.vn", "password": "..." }
```

Response (200):
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 3600,
  "admin": { "id": 1, "email": "phuong@betien.vn", "role": "super_admin" }
}
```

Errors: 401 (invalid credentials), 429 (rate limited).

#### `GET /api/admin/auth/me`

Headers: `Authorization: Bearer <token>`

Response (200): admin info + permissions.

#### `POST /api/admin/auth/logout`

Invalidate token (add to Redis blacklist with TTL = remaining token lifetime).

### 7.3. Stats overview

#### `GET /api/admin/stats/overview`

Query params: `period` (default `30d`, options: `7d`, `14d`, `30d`, `90d`).

Response (200):
```json
{
  "period": "30d",
  "generated_at": "2026-05-13T08:00:00+07:00",
  "metrics": {
    "total_users": 47,
    "total_users_delta_pct": 12,
    "new_users_period": 12,
    "dau": 23,
    "dau_delta_pct": 8,
    "wau": 38,
    "mau": 45,
    "stickiness_pct": 51,
    "activation_rate_pct": 64,
    "total_llm_cost_usd": 4.32,
    "cost_delta_pct": -15,
    "avg_cost_per_active_user": 0.187,
    "asset_coverage_pct": 68,
    "briefing_open_rate_pct": 73,
    "error_rate_pct": 2.1
  }
}
```

**Caching**: Redis TTL = 5 phút. Key: `admin:stats:overview:{period}`.

### 7.4. Charts endpoints

#### `GET /api/admin/charts/user-growth?days=30`

Response:
```json
{
  "data": [
    { "date": "2026-04-13", "cumulative": 12, "new_users": 2 },
    { "date": "2026-04-14", "cumulative": 13, "new_users": 1 }
  ]
}
```

#### `GET /api/admin/charts/dau?days=14`

Response:
```json
{
  "data": [
    { "date": "2026-04-30", "dau": 14 },
    { "date": "2026-05-01", "dau": 16 }
  ]
}
```

#### `GET /api/admin/charts/feature-clicks?days=30&limit=10`

Response:
```json
{
  "data": [
    { "feature_key": "total_assets", "feature_name": "Tổng tài sản", "clicks": 412 },
    { "feature_key": "morning_briefing", "feature_name": "Briefing sáng", "clicks": 387 }
  ]
}
```

#### `GET /api/admin/charts/intent-breakdown?days=7`

Response:
```json
{
  "data": [
    { "resolved_by": "rule", "label": "Rule-based (zero cost)", "count": 1820, "pct": 73 },
    { "resolved_by": "llm_classifier", "label": "LLM classified", "count": 548, "pct": 22 },
    { "resolved_by": "clarification", "label": "Cần clarify", "count": 125, "pct": 5 }
  ]
}
```

#### `GET /api/admin/charts/user-tiers`

Response:
```json
{
  "data": [
    { "tier": "starter", "label": "Starter", "count": 21 },
    { "tier": "young_pro", "label": "Young Pro", "count": 18 },
    { "tier": "mass_affluent", "label": "Mass Affluent", "count": 7 },
    { "tier": "hnw", "label": "HNW", "count": 1 }
  ]
}
```

#### `GET /api/admin/charts/cohort-retention?weeks=8`

Response:
```json
{
  "cohorts": [
    {
      "cohort_week": "2026-04-13",
      "cohort_size": 12,
      "retention": { "w0": 100, "w1": 75, "w2": 67, "w3": 58, "w4": 50 }
    }
  ]
}
```

### 7.5. User management

#### `GET /api/admin/users`

Query params:
- `search` (string, search trong user_id, name, telegram_username)
- `tier` (string, filter)
- `status` (string: `active` / `at_risk` / `dormant` / `new`)
- `sort` (string: `last_active_desc` / `cost_desc` / `joined_desc`)
- `limit` (int, default 50, max 200)
- `offset` (int, default 0)

Response:
```json
{
  "total": 47,
  "limit": 50,
  "offset": 0,
  "users": [
    {
      "user_id": "tg_8412",
      "display_name": "Nguyễn V. A.",
      "tier": "mass_affluent",
      "joined_at": "2026-04-12",
      "last_active_at": "2026-05-13T06:00:00+07:00",
      "last_active_human": "2 giờ trước",
      "messages_total": 234,
      "tokens_total": 48230,
      "llm_cost_total_usd": 0.42,
      "assets_count": 6,
      "status": "active"
    }
  ]
}
```

#### `GET /api/admin/users/{user_id}`

Response: chi tiết 1 user gồm timeline activity, asset list, cost breakdown.

#### `PATCH /api/admin/users/{user_id}/status`

Body: `{ "status": "suspended", "reason": "..." }`. Ghi audit log.

### 7.6. Audit log

#### `GET /api/admin/audit?limit=50`

Response: list các admin action.

### 7.7. Health endpoint

#### `GET /api/admin/system/health`

Response: DB connection, Redis connection, last data sync time.

---

## 8. Database Schema & Queries

### 8.1. New tables

> **⚠ Schema dependency**: Story 1.5 trong issues.md sẽ thêm cột `resolved_by VARCHAR(50)` vào bảng `messages` hiện có. Cột này (`rule` / `llm_classifier` / `clarification`) là output của Phase 3.5 Intent Layer dispatcher. Phase 3.6 query depends on column này.

#### `admin_users`

```sql
CREATE TABLE admin_users (
  id              SERIAL PRIMARY KEY,
  email           VARCHAR(255) UNIQUE NOT NULL,
  password_hash   VARCHAR(255) NOT NULL,
  full_name       VARCHAR(255),
  role            VARCHAR(50) NOT NULL DEFAULT 'super_admin',
  tenant_id       INTEGER,
  is_active       BOOLEAN DEFAULT TRUE,
  last_login_at   TIMESTAMPTZ,
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_admin_users_email ON admin_users(email);
```

#### `admin_audit_log`

```sql
CREATE TABLE admin_audit_log (
  id              BIGSERIAL PRIMARY KEY,
  admin_user_id   INTEGER REFERENCES admin_users(id),
  action          VARCHAR(100) NOT NULL,
  target_type     VARCHAR(50),
  target_id       VARCHAR(255),
  payload         JSONB,
  ip_address      INET,
  user_agent      TEXT,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audit_admin_user ON admin_audit_log(admin_user_id);
CREATE INDEX idx_audit_created_at ON admin_audit_log(created_at DESC);
CREATE INDEX idx_audit_target ON admin_audit_log(target_type, target_id);
```

#### `feature_events` (nếu chưa có)

```sql
CREATE TABLE feature_events (
  id              BIGSERIAL PRIMARY KEY,
  user_id         VARCHAR(50) NOT NULL,
  tenant_id       INTEGER NOT NULL,
  feature_key     VARCHAR(100) NOT NULL,
  metadata        JSONB,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_feature_events_user ON feature_events(user_id);
CREATE INDEX idx_feature_events_feature ON feature_events(feature_key, created_at DESC);
CREATE INDEX idx_feature_events_created ON feature_events(created_at DESC);
```

#### `licenses` (placeholder cho Phase 5)

```sql
CREATE TABLE licenses (
  id              SERIAL PRIMARY KEY,
  user_id         VARCHAR(50) UNIQUE NOT NULL,
  tenant_id       INTEGER NOT NULL,
  plan            VARCHAR(50) NOT NULL DEFAULT 'free',
  status          VARCHAR(50) NOT NULL DEFAULT 'active',
  trial_started_at  TIMESTAMPTZ,
  trial_ends_at     TIMESTAMPTZ,
  paid_started_at   TIMESTAMPTZ,
  next_renewal_at   TIMESTAMPTZ,
  cancelled_at      TIMESTAMPTZ,
  metadata          JSONB,
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_licenses_user ON licenses(user_id);
CREATE INDEX idx_licenses_status ON licenses(status, next_renewal_at);
```

### 8.2. Reference queries

#### Overview stats (single call cho dashboard hero)

```sql
WITH
  total_users AS (SELECT COUNT(*) AS c FROM users WHERE tenant_id = :tenant),
  users_30d_ago AS (
    SELECT COUNT(*) AS c FROM users
    WHERE tenant_id = :tenant AND created_at < NOW() - INTERVAL '30 days'
  ),
  dau AS (
    SELECT COUNT(DISTINCT user_id) AS c FROM messages
    WHERE tenant_id = :tenant AND created_at >= CURRENT_DATE
  ),
  mau AS (
    SELECT COUNT(DISTINCT user_id) AS c FROM messages
    WHERE tenant_id = :tenant AND created_at >= NOW() - INTERVAL '30 days'
  ),
  llm_cost AS (
    SELECT COALESCE(SUM(cost_usd), 0) AS c FROM llm_calls
    WHERE tenant_id = :tenant AND created_at >= DATE_TRUNC('month', NOW())
  ),
  asset_coverage AS (
    SELECT
      COUNT(DISTINCT a.user_id)::float / NULLIF((SELECT c FROM total_users), 0) * 100 AS pct
    FROM assets a
    JOIN users u ON a.user_id = u.user_id
    WHERE u.tenant_id = :tenant AND a.deleted_at IS NULL
  )
SELECT
  (SELECT c FROM total_users) AS total_users,
  ROUND(
    ((SELECT c FROM total_users) - (SELECT c FROM users_30d_ago))::float
    / NULLIF((SELECT c FROM users_30d_ago), 0) * 100
  )::int AS total_users_delta_pct,
  (SELECT c FROM dau) AS dau,
  (SELECT c FROM mau) AS mau,
  ROUND((SELECT c FROM dau)::float / NULLIF((SELECT c FROM mau), 0) * 100) AS stickiness_pct,
  ROUND((SELECT c FROM llm_cost)::numeric, 2) AS total_llm_cost_usd,
  ROUND((SELECT pct FROM asset_coverage)::numeric, 1) AS asset_coverage_pct;
```

#### Cumulative user growth

```sql
SELECT
  DATE(created_at) AS date,
  COUNT(*) AS new_users,
  SUM(COUNT(*)) OVER (ORDER BY DATE(created_at)) AS cumulative
FROM users
WHERE tenant_id = :tenant
  AND created_at >= NOW() - INTERVAL ':days days'
GROUP BY DATE(created_at)
ORDER BY date;
```

#### Cohort retention matrix

```sql
WITH user_cohorts AS (
  SELECT
    user_id,
    DATE_TRUNC('week', created_at)::date AS cohort_week
  FROM users
  WHERE tenant_id = :tenant
),
weekly_activity AS (
  SELECT DISTINCT
    user_id,
    DATE_TRUNC('week', created_at)::date AS active_week
  FROM messages
  WHERE tenant_id = :tenant
),
cohort_size AS (
  SELECT cohort_week, COUNT(*) AS size FROM user_cohorts GROUP BY cohort_week
),
retention_raw AS (
  SELECT
    uc.cohort_week,
    cs.size,
    ((wa.active_week - uc.cohort_week) / 7)::int AS week_offset,
    COUNT(DISTINCT uc.user_id) AS retained
  FROM user_cohorts uc
  JOIN weekly_activity wa ON uc.user_id = wa.user_id
  JOIN cohort_size cs ON uc.cohort_week = cs.cohort_week
  WHERE wa.active_week >= uc.cohort_week
  GROUP BY uc.cohort_week, cs.size, week_offset
)
SELECT
  cohort_week,
  size,
  week_offset,
  ROUND(retained::float * 100 / size)::int AS retention_pct
FROM retention_raw
WHERE cohort_week >= NOW() - INTERVAL ':weeks weeks'
ORDER BY cohort_week DESC, week_offset;
```

#### Intent breakdown (Phase 3.5 monitoring)

```sql
SELECT
  resolved_by,
  COUNT(*) AS count,
  ROUND((COUNT(*)::float * 100 / SUM(COUNT(*)) OVER ())::numeric, 1) AS pct
FROM messages
WHERE tenant_id = :tenant
  AND created_at >= NOW() - INTERVAL ':days days'
  AND resolved_by IS NOT NULL
GROUP BY resolved_by;
```

#### User status classification

```sql
-- Trong service layer, dùng output này để gán status:
SELECT
  u.user_id,
  EXTRACT(EPOCH FROM (NOW() - COALESCE(MAX(m.created_at), u.created_at))) / 86400 AS days_inactive,
  CASE
    WHEN u.created_at >= NOW() - INTERVAL '3 days' THEN 'new'
    WHEN MAX(m.created_at) IS NULL OR MAX(m.created_at) < NOW() - INTERVAL '7 days' THEN 'dormant'
    WHEN MAX(m.created_at) < NOW() - INTERVAL '3 days' THEN 'at_risk'
    ELSE 'active'
  END AS status
FROM users u
LEFT JOIN messages m ON u.user_id = m.user_id
WHERE u.tenant_id = :tenant
GROUP BY u.user_id, u.created_at;
```

### 8.3. Performance notes

- Các query analytics nặng → cache trong Redis 5 phút.
- Cohort retention query đặc biệt nặng → có thể chạy nightly job và cache 24h.
- Tạo materialized view cho metrics ổn định (daily aggregates).

---

## 9. Frontend Architecture

### 9.1. Component tree

```
<App>
  <AuthProvider>
    <Router>
      <Route /login>
        <LoginPage />
      </Route>
      <ProtectedRoute>
        <DashboardLayout>
          <Header />
          <HeroSection />
          <KPIGrid>
            <KPICard /> × 6
          </KPIGrid>
          <ChartGrid>
            <UserGrowthChart />
            <DAUChart />
            <FeatureClicksChart />
            <IntentBreakdownChart />
            <TierDistributionChart />
            <CohortRetentionTable />
          </ChartGrid>
          <UserDirectory>
            <SearchFilterBar />
            <UserTable />
            <Pagination />
          </UserDirectory>
          <LicensePlaceholder />
        </DashboardLayout>
      </ProtectedRoute>
    </Router>
  </AuthProvider>
</App>
```

### 9.2. State management

- **Auth state**: Context API + localStorage cho token. Token expiry handled bằng axios-like interceptor (refresh hoặc redirect login).
- **Dashboard state**: useState/useReducer trong từng component. Không cần Redux.
- **Server state caching**: Có thể dùng SWR hoặc TanStack Query nếu cần — v1.0 dùng plain fetch + useState đủ.

### 9.3. API client wrapper

```javascript
// src/api/client.js
const API_BASE = import.meta.env.VITE_API_BASE || '/api/admin';

async function request(path, options = {}) {
  const token = localStorage.getItem('admin_token');
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token && { Authorization: `Bearer ${token}` }),
      ...options.headers
    }
  });
  if (res.status === 401) {
    localStorage.removeItem('admin_token');
    window.location.href = '/login';
    return;
  }
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export const api = {
  login: (email, password) => request('/auth/login', {
    method: 'POST', body: JSON.stringify({ email, password })
  }),
  getOverview: (period = '30d') => request(`/stats/overview?period=${period}`),
  getUserGrowth: (days = 30) => request(`/charts/user-growth?days=${days}`),
  getDAU: (days = 14) => request(`/charts/dau?days=${days}`),
  getFeatureClicks: (days = 30) => request(`/charts/feature-clicks?days=${days}`),
  getIntentBreakdown: (days = 7) => request(`/charts/intent-breakdown?days=${days}`),
  getUserTiers: () => request('/charts/user-tiers'),
  getCohortRetention: (weeks = 8) => request(`/charts/cohort-retention?weeks=${weeks}`),
  getUsers: (params) => request(`/users?${new URLSearchParams(params)}`),
  getUserDetail: (userId) => request(`/users/${userId}`),
};
```

### 9.4. Design tokens (Tailwind config)

```javascript
// tailwind.config.js
export default {
  theme: {
    extend: {
      colors: {
        bg: '#FAF7F2',
        'bg-card': '#FFFFFF',
        'bg-card-alt': '#F5F1EA',
        ink: {
          900: '#0A2540',
          700: '#2C3E50',
          500: '#5C6B7A',
          300: '#A5B0BC'
        },
        line: '#E8E0D3',
        gold: { DEFAULT: '#B8945A', dark: '#8B6F3D' },
        sage: '#5A7A4F',
        burgundy: '#8B2635',
        warm: '#C97B4A'
      },
      fontFamily: {
        display: ['Fraunces', 'Georgia', 'serif'],
        body: ['Geist', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace']
      }
    }
  }
};
```

---

## 10. UI/UX Specifications

### 10.1. Aesthetic direction

**Financial editorial** — kết hợp giữa Bloomberg Terminal (data-dense, professional) và Financial Times (typography đẹp, refined). Đối lập hoàn toàn với "AI slop dashboards" (purple gradient, generic Inter font).

### 10.2. Layout & breakpoints

- **Desktop (≥1024px)**: 6 cột KPI grid, 2-3 cột chart grid.
- **Tablet (768-1023px)**: 3 cột KPI, 2 cột chart.
- **Mobile (375-767px)**: 2 cột KPI, 1 cột chart, table scroll horizontal.

### 10.3. Typography hierarchy

| Element | Font | Size | Weight |
|---------|------|------|--------|
| Hero number | Fraunces | 36-48px | 600 |
| Section title | Fraunces | 18-24px | 500 |
| Body text | Geist | 14px | 400 |
| Label (uppercase) | Geist | 10-11px | 500 |
| Data/number | JetBrains Mono | 12-14px | 500 |

### 10.4. Color usage rules

- **Gold (#B8945A)**: Accent, hero numbers, primary action.
- **Ink-900 (#0A2540)**: Primary text, dark CTAs.
- **Sage (#5A7A4F)**: Positive delta, success state.
- **Burgundy (#8B2635)**: Negative delta, warning, dormant status.
- **Warm orange (#C97B4A)**: At-risk status.

Không dùng gradient (trừ subtle area chart fill). Không drop shadow heavy. Border 1px hairline #E8E0D3 thay vì shadow.

### 10.5. Empty/loading/error states

- **Loading**: Skeleton screens với shimmer (không spinner).
- **Empty**: "Chưa có dữ liệu cho period này" + icon.
- **Error**: "Không tải được. Click để retry." + retry button.

### 10.6. Accessibility

- Contrast ratio ≥4.5:1 cho text thường, ≥3:1 cho large text.
- Tất cả button có `aria-label`.
- Keyboard navigation: Tab/Enter/Esc.
- Color không phải signal duy nhất (luôn kèm icon/text).

---

## 11. Security

### 11.1. Authentication

- **JWT** với HS256, expiry 1 giờ, refresh token expiry 7 ngày.
- Password hash bằng **bcrypt** cost factor ≥12.
- Login rate limit: 5 attempts / 15 phút / IP.
- Token revocation qua Redis blacklist.

### 11.2. Authorization (v1.0)

Chỉ 1 role `super_admin`. Kiểm tra trong dependency `get_current_admin()`.

### 11.3. PII protection

- Bảng user list chỉ hiển thị tên dạng initials: `Nguyễn V. A.`.
- Email/SĐT chỉ hiện khi click vào user detail và bị mask một phần.
- Tất cả PII fields require role check trong service layer.
- Logs không được chứa raw PII.

### 11.4. Audit log

Mọi admin action ghi vào `admin_audit_log`. Các action cần log:
- Login/logout (thành công và thất bại)
- View user detail (track xem user nào, lúc nào)
- Change user status
- (Tương lai) License changes, refunds

### 11.5. Network security

- HTTPS bắt buộc (Caddy auto-SSL).
- Subdomain riêng: `admin.betien.vn`.
- CORS chỉ allow `admin.betien.vn` cho `/api/admin/*`.
- IP whitelist tùy chọn (chỉ Việt Nam + IP cố định của Phuong).
- Rate limit: 100 req/min/IP cho `/api/admin/*`.

### 11.6. Sensitive data tại rest

- Password hash bcrypt.
- JWT secret rotation 6 tháng.
- Backup encrypted.

---

## 12. Deployment

### 12.1. Build process

```bash
# Trong betien-admin/ (Vite project)
npm install
npm run build
# Output: dist/

# Copy dist content vào FastAPI static
cp -r dist/* ../be_tien_backend/app/static/admin/
```

### 12.2. FastAPI integration

```python
# app/main.py
from fastapi.staticfiles import StaticFiles

app.mount(
    "/admin",
    StaticFiles(directory="app/static/admin", html=True),
    name="admin"
)
```

### 12.3. Caddy config (admin.betien.vn)

```caddyfile
admin.betien.vn {
    tls phuong@betien.vn

    # Rate limit
    rate_limit {
        zone admin_api {
            key {remote_ip}
            events 100
            window 1m
        }
    }

    # API
    handle /api/admin/* {
        reverse_proxy localhost:8000
    }

    # Static admin SPA
    handle {
        reverse_proxy localhost:8000
    }

    # Security headers
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "strict-origin-when-cross-origin"
    }
}
```

### 12.4. Environment variables

```
# .env (backend)
ADMIN_JWT_SECRET=<random 64-char, generate by `openssl rand -hex 32`>
ADMIN_JWT_EXPIRY_MINUTES=60
ADMIN_RATE_LIMIT_REDIS_URL=redis://localhost:6379/1
ADMIN_ALLOWED_IPS=<comma-separated, optional>

# Initial seed (chỉ dùng lần đầu, xóa sau khi seed xong)
INITIAL_ADMIN_EMAIL=phuongphh@nuitruc.ai
INITIAL_ADMIN_PASSWORD=admin
# ⚠ Password "admin" yếu — force_password_change=true sẽ bắt buộc đổi
# ngay lần login đầu tiên (xem Story 1.1, 1.2).

# .env (frontend, build-time)
VITE_API_BASE=https://admin.betien.vn/api/admin
```

### 12.5. Migration plan

1. Apply migrations cho 4 bảng mới (`admin_users`, `admin_audit_log`, `feature_events`, `licenses`).
2. Seed 1 admin user.
3. Backfill `feature_events` từ existing logs nếu có.
4. Deploy backend trước.
5. Deploy frontend.
6. Update DNS cho `admin.betien.vn`.
7. Test end-to-end.

---

## 13. Performance & Scalability

### 13.1. Current scale (soft launch)

- ~50 users → mọi query chạy trong <50ms.
- DAU ~25, MAU ~45 → data volume rất nhỏ.

### 13.2. Scalability concerns khi đạt 10k users

- Cohort retention query sẽ chậm (>5s) → cần materialized view, refresh nightly.
- `messages` table sẽ lớn → cần partition by month.
- `feature_events` cần được aggregate sang daily summary table.
- Consider migrating analytics queries sang ClickHouse hoặc TimescaleDB.

### 13.3. Caching strategy

- Overview stats: Redis 5 phút TTL.
- Chart data (30 ngày): Redis 30 phút TTL.
- Cohort retention: Redis 24h TTL, invalidate nightly.
- User list: không cache (cần fresh).

### 13.4. Future migration path (Mac Mini → Cloud)

Khi cần scale lên cloud-native Kubernetes:
- Backend FastAPI → containerize, deploy lên GKE/EKS.
- PostgreSQL → managed (CloudSQL, RDS).
- Redis → managed (MemoryStore, ElastiCache).
- Static admin SPA → CDN (Cloudfront, CloudFlare).

---

## 14. Roadmap & Future

### v1.0 (current — Phase 3.6)

Scope đã liệt kê trong Section 3. Target launch: cuối tuần 8 soft launch.

### v1.1 (Phase 3.6.1)

- Export users/metrics ra CSV/Excel.
- Customizable date range picker.
- Dark mode.
- Saved filter presets.

### v1.2 (Phase 3.6.2)

- Alert system: Slack/email notification khi metric vượt threshold.
- Daily digest email cho admin.
- Funnel analysis (signup → first asset → first briefing → retained).

### v2.0 (Phase 5 — License Management)

Activate placeholder sang full implementation:

- **License lifecycle**: Free → Trial → Paid → Cancelled.
- **Plan management**: Free / Pro / HNW tiers với feature gates.
- **Billing**: Tích hợp VNPay/MoMo, MoMo, hoặc Stripe.
- **Revenue metrics**: MRR, ARR, churn, LTV, ARPU, CAC.
- **Trial conversion funnel**: D0 → D7 → D14 → paid.
- **Churn risk scoring**: ML model dựa trên engagement signals.
- **Customer support tools**: View conversation, refund, plan change.

### v3.0 (Phase 6 — Multi-tenant SaaS)

- Multi-admin với RBAC.
- Tenant isolation enforcement.
- White-label cho enterprise customer.

---

## 15. Architecture Decision Records (ADR)

### ADR-001: React SPA vs Server-rendered HTML

**Decision**: React SPA build with Vite.

**Rationale**:
- Interactive charts cần re-render dynamic — server-rendered awkward.
- Decoupled from backend codebase → có thể migrate sang Next.js sau.
- Ecosystem (Recharts, Lucide) production-ready.
- Build output là static files → deploy đơn giản.

**Trade-off**: Initial bundle size lớn hơn (~200KB gzipped). Chấp nhận được cho internal tool.

### ADR-002: Tích hợp với FastAPI thay vì microservice riêng

**Decision**: Admin API là namespace `/api/admin/*` trong FastAPI hiện có.

**Rationale**:
- Tái dùng DB connection, ORM, business logic services.
- Đơn giản hóa deployment (1 backend thay vì 2).
- Scope hiện tại nhỏ, không cần tách.

**Trade-off**: Admin code mix với core code. Mitigate bằng namespacing rõ ràng.

### ADR-003: JWT thay vì session-based auth

**Decision**: JWT với short expiry (1h) + refresh token.

**Rationale**:
- Stateless, dễ scale.
- Tách biệt admin auth khỏi user auth (Telegram-based).
- Industry standard.

**Trade-off**: Cần Redis blacklist cho logout. Acceptable.

### ADR-004: Tách Vite project riêng thay vì serve React qua FastAPI Jinja

**Decision**: Separate `betien-admin/` directory, build ra static, FastAPI serve static.

**Rationale**:
- Dev experience tốt hơn (HMR, fast refresh).
- Có thể migrate sang Next.js + Vercel sau mà không động backend.

### ADR-005: Recharts thay vì D3 hoặc Chart.js

**Decision**: Recharts.

**Rationale**:
- Declarative API hợp React.
- Responsive built-in.
- Đủ chart types cho v1.0.

**Trade-off**: Less flexible hơn D3 cho custom viz. Nếu cần advanced cohort heatmap có thể fallback sang D3.

### ADR-006: License model tạo từ v1.0 dù chưa dùng

**Decision**: Tạo bảng `licenses` ngay trong Phase 3.6, default plan="free" cho tất cả user.

**Rationale**:
- Tránh migration đau đầu sau.
- Sẵn sàng activate khi launch paid tier.
- Cost = 1 migration, benefit = clean roadmap.

---

## 16. Open Questions

> **Update 2026-05-13**: Q1, Q2, Q5 (partial) đã được trả lời bởi Phuong.

1. ~~**Admin user count v1.0**~~ → **RESOLVED**: Chỉ Phuong trong v1.0. Initial seed: `phuongphh@nuitruc.ai`. Password mặc định là dev placeholder, phải đổi ngay sau lần login đầu qua endpoint change-password.

2. ~~**Phase 3.5 `resolved_by` column**~~ → **RESOLVED**: Column chưa tồn tại trong bảng `messages` (Phase 3.5 mới design, chưa implement). Phase 3.6 phải tự handle migration này như pre-requisite của Story 2.4 (xem `AdminDashboard-issues.md` Epic 0).

3. **Date range cho cohort retention**: Mặc định 8 tuần hay 12 tuần? → Soft launch mới 5 tuần, có thể 8 tuần là đủ.

4. **Notification channel v1.0**: Có cần Telegram/email alert cho admin ngay từ v1.0 không? → Đã đặt vào v1.2 nhưng có thể sớm hơn nếu thấy cần.

5. **PDPA compliance**: Việt Nam có quy định PDPA mới — cần review xem dashboard hiển thị bao nhiêu PII là an toàn về mặt pháp lý.

6. **License plan structure**: Khi sẵn sàng activate, định nghĩa cụ thể của Free/Pro/HNW tier (feature gates, price point) — defer đến lúc planning Phase 5.

7. **Backup admin access**: Nếu Phuong mất quyền truy cập (mất password, lost 2FA), recovery flow thế nào? → Cần emergency recovery procedure.

8. **Materialized view refresh schedule**: Khi nào thì chuyển từ on-demand query sang materialized view? → Quyết định khi DAU >500 hoặc query latency >2s.

---

**Document version**: 1.0
**Last updated**: 2026-05-13
**Next review**: Khi hoàn thành Sprint 1
