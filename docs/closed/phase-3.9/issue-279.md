# Issue #279

[Story] P3.9-S12: Gold price auto-updater + wealth integration

**Parent Epic:** #265 (Epic 3: Gold + Bank Rates + News)

## User Story
As a system, I need gold updater cron 3 lần/ngày + wealth valuation integration.

## Acceptance Criteria
- [ ] `app/market_data/jobs/gold_updater.py` cron 0 9,13,16 * * *
- [ ] `app/wealth/valuation/gold.py` updated tương tự S9 (real price)
- [ ] Fallback: SJC fail → PNJ → user_input_price + stale flag

## Estimate: ~0.5 day
## Depends on: P3.9-S11
