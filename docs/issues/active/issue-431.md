# Issue #431

[Story] P4B-S14: Recurring Transaction Detector

**Parent Epic:** #416 (Epic 3: Cashflow Forecasting v2)

## User Story
Tôi muốn Bé Tiền tự nhận ra lương, tiền nhà và các khoản cố định.

## Implementation Tasks
- [ ] Alembic migration: recurring_patterns table
- [ ] cashflow/detector.py: rule-based detection (amount_band + day_band)
- [ ] Cron Monday 06:00 AM weekly
- [ ] Only process users with >= 3 months history

## Estimate: ~1.5 days
## Dependencies: Existing transaction history

Close #416
