# Issue #81

[P3A-23] Chart.js integration: pie chart + trend line chart

## Epic
Epic 4 — Visualization & Testing | **Week 4** | Depends: P3A-21, P3A-22

## Description
Interactive charts với Chart.js. Vietnamese money format. Smooth animations.

## Acceptance Criteria
- [x] File `app/miniapp/static/js/wealth_dashboard.js`
- [ ] Doughnut chart cho asset type breakdown
- [ ] Line chart cho net worth trend
- [ ] Tooltips format tiền Việt: "1.5tr" thay vì "1,500,000"
- [ ] Period selector: [30 ngày] [90 ngày] [365 ngày] — re-fetch và re-render
- [ ] Colors map từ `asset_categories.yaml`
- [ ] Responsive: charts resize theo screen width
- [ ] Click pie slice → highlight + show detail tooltip
- [ ] Charts load async sau page render (không block UI)
- [ ] Skeleton placeholder khi loading

## Technical Notes
- Chart.js 4.4.0

## Estimate
~1 day
