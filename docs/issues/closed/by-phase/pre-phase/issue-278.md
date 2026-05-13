# Issue #278

[Story] P3.9-S11: PNJ gold scraper (backup)

**Parent Epic:** #265 (Epic 3: Gold + Bank Rates + News)

## User Story
As a system, I need PNJ scraper backup cho khi SJC parser break.

## Acceptance Criteria
- [ ] `app/market_data/providers/gold_pnj.py`
- [ ] `gold_dispatcher.py` dùng Dispatcher(SJC, PNJ, timeout=5.0)
- [ ] Fixture HTML PNJ
- [ ] Unit + integration tests

## Estimate: ~0.5 day
## Depends on: P3.9-S3, P3.9-S10
