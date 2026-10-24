# Issue #274

[Story] P3.9-S7: Stock price auto-updater (cron job)

**Parent Epic:** #264 (Epic 2: Stock + Crypto Providers)

## User Story
As a system, I need background job pre-warm cache cho mọi stock user hold, chạy 15 phút trong giờ giao dịch.

## Acceptance Criteria
- [ ] `app/market_data/jobs/stock_updater.py` — update_all_held_stocks()
- [ ] Query distinct symbols từ stock_holdings → batch fetch → write cache (regular + last_known)
- [ ] Schedule: cron */15 9-15 * * 1-5 (HOSE trading hours, Asia/Ho_Chi_Minh)
- [ ] Register trong APScheduler
- [ ] Metrics: symbols_attempted, symbols_succeeded, duration_ms
- [ ] No-op nếu không có stock

## Estimate: ~0.5 day
## Depends on: P3.9-S5, P3.9-S2
