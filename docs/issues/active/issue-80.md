# Issue #80

[P3A-22] Implement /api/wealth/overview endpoint

## Epic
Epic 4 — Visualization & Testing | **Week 4** | Depends: P3A-4, P3A-5 | Blocks: P3A-23

## Description
FastAPI endpoint trả về toàn bộ data cho wealth dashboard. Performance critical.

## Acceptance Criteria
- [ ] Route `GET /miniapp/api/wealth/overview`
- [x] Auth: `require_miniapp_auth` (Telegram initData)
- [ ] Response JSON schema:
  ```json
  {
    "net_worth": 150000000,
    "level": "young_professional",
    "change_day": {"amount": 500000, "pct": 0.33},
    "change_month": {"amount": 2000000, "pct": 1.35},
    "breakdown": [{"type": "cash", "label": "Tiền mặt", "icon": "💵", "value": ..., "pct": ..., "color": ...}],
    "trend_90d": [{"date": "2025-01-01", "value": ...}],
    "assets": [{"id": ..., "name": ..., "type": ..., "value": ...}],
    "next_milestone": {"target": 200000000, "label": "Mass Affluent", "pct_progress": 75}
  }
  ```
- [ ] Performance: <500ms cho user có 10+ assets
- [ ] Sub-endpoint: `GET /miniapp/api/wealth/trend?days=30|90|365`
- [ ] Cache response 30 giây (Redis hoặc in-memory)
- [ ] Error: 401 auth fail, 500 graceful với message

## Estimate
~1 day

## Reference
`docs/current/phase-3a-detailed.md` § 4.1
