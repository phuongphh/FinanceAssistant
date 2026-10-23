# Issue #284

[Story] P3.9-S17: Portfolio analytics (YTD, best/worst, diversification)

**Parent Epic:** #266 (Epic 4: Enhanced Briefing + Analytics + Alerts)

## User Story
As a user, I want YTD return, best/worst performer, và diversification score.

## Acceptance Criteria
- [ ] `app/market_data/analytics/portfolio_metrics.py`
- [ ] compute_ytd_return(user_id) → {available, return_pct, absolute, by_holding: [...]}
- [ ] get_best_worst_performer(user_id) → (top_holding, bottom_holding)
- [ ] compute_diversification_score(portfolio) → int (0-100) + label (Tốt/Trung bình/Yếu)
- [ ] Job historical_price_seeder.py — cron 0 7 1 1 * (đầu năm)
- [ ] DB migration: stock_historical_prices table
- [ ] Unit tests 3 functions
- [ ] Briefing template (S16) reference các metric này

## Estimate: ~1 day
## Depends on: P3.9-S9, P3.9-S16
