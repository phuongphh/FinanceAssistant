# Issue #29

[Phase 1 - Week 3] Telegram Mini App — Dashboard v1

## User Story
As a user, I want to open a beautiful in-app dashboard from the Telegram menu button to see my monthly spending overview, category breakdown, and daily trend — without leaving Telegram.

## Background
Phase 1 - Week 3. Requires HTTPS domain (ngrok or real VPS for dev).

## Tasks

### Backend
- [ ] Create `app/miniapp/auth.py`
  - `verify_init_data(init_data)` — HMAC verification per Telegram spec
  - `require_miniapp_auth` — FastAPI dependency (reads `X-Telegram-Init-Data` header)
- [ ] Create `app/miniapp/routes.py`
  - `GET /miniapp/dashboard` — serves HTML page (no auth)
  - `GET /miniapp/api/overview` — monthly total, transaction count, category breakdown, daily trend (auth required)
  - `GET /miniapp/api/recent-transactions` — last N transactions (auth required)
- [ ] Extend `ReportService` with: `get_month_total`, `get_month_transaction_count`, `get_category_breakdown`, `get_daily_trend(days=30)`
- [ ] Register `miniapp.routes` in FastAPI app

### Frontend
- [ ] Create `app/miniapp/templates/dashboard.html` — loads Telegram WebApp SDK + Chart.js
- [ ] Create `app/miniapp/static/js/dashboard.js`
  - Initialize `window.Telegram.WebApp`, apply theme colors
  - Fetch /overview and render: total amount card, doughnut chart, category list with bars, line trend chart
- [ ] Create `app/miniapp/static/css/style.css` — mobile-first, Telegram theme aware

### Setup
- [ ] Register Mini App URL in BotFather (Menu Button → Dashboard)
- [ ] Write `tests/test_miniapp_auth.py` for `verify_init_data`

## Acceptance Criteria
- [ ] Menu button in Telegram chat opens the Mini App
- [ ] Dashboard loads in <2 seconds
- [ ] Total monthly spending shown correctly
- [ ] Category doughnut chart renders with correct colors
- [ ] Daily trend line chart shows last 30 days
- [ ] Works correctly on both iPhone and Android (test on real devices)
- [ ] Invalid/missing auth header returns 401

## Reference
`docs/strategy/phase-1-detailed.md` — Sections 3.1 – 3.4
