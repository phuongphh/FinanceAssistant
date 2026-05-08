# Issue #272

[Story] P3.9-S5: VNDIRECT stock provider (backup)

**Parent Epic:** #264 (Epic 2: Stock + Crypto Providers)

## User Story
As a system, I need VNDIRECT backup khi SSI unavailable.

## Acceptance Criteria
- [ ] `app/market_data/providers/stock_vndirect.py` tương tự SSI
- [ ] Schema VNDIRECT khác SSI → normalize về cùng PriceQuote
- [ ] `stock_dispatcher.py` dùng Dispatcher(SSI, VNDIRECT, timeout=3.0)
- [ ] Unit tests VNDIRECT parser
- [ ] Integration test: mock SSI fail → verify VNDIRECT gọi

## Estimate: ~0.5 day
## Depends on: P3.9-S3, P3.9-S4
