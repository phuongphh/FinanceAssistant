# Issue #79

[P3A-21] Build Mini App net worth dashboard HTML/CSS

## Epic
Epic 4 — Visualization & Testing | **Week 4** | Depends: Phase 1 Mini App | Blocks: P3A-23

## Description
"North Star" screen — nơi user xem tổng tài sản. Phải đẹp, fast load, mobile-first.

## Acceptance Criteria
- [x] File `app/miniapp/templates/net_worth_dashboard.html`
- [x] File `app/miniapp/static/css/wealth.css`
- [x] 6 sections:
  1. **Hero card**: Net worth total + change vs yesterday
  2. **Pie chart**: Asset type breakdown
  3. **Breakdown list**: icon + label + value + percentage
  4. **Trend chart**: Line 30/90/365 ngày (period selector)
  5. **Milestone section** (Starter only)
  6. **Assets list** với edit button
- [x] Responsive: iPhone SE (375px) → Pro Max (430px)
- [x] Loading skeleton state (trước khi data về)
- [x] Empty state: "Bắt đầu bằng việc thêm tài sản đầu tiên" + CTA button
- [x] Dark mode: read `Telegram.WebApp.themeParams` and apply CSS variables
- [ ] `Telegram.WebApp.expand()` để full screen
- [ ] Load time < 1.5s trên 4G

## Technical Notes
- Vanilla JS (không React/Vue — giữ nhẹ)
- Chart.js 4.4.0 từ CDN
- CSS variables cho Telegram theme

## Estimate
~1.5 day

## Reference
`docs/current/phase-3a-detailed.md` § 4.1
