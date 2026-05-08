# Issue #277

[Story] P3.9-S10: SJC gold scraper (primary)

**Parent Epic:** #265 (Epic 3: Gold + Bank Rates + News)

## User Story
As a system, I need to scrape SJC website cho giá vàng — loại phổ biến nhất ở VN.

## Acceptance Criteria
- [ ] `app/market_data/providers/gold_sjc.py` với class `SJCGoldProvider(BaseProvider)`
- [ ] fetch_quote(symbol="SJC_GOLD" | "RING_24K") parse HTML từ SJC
- [ ] Fixture HTML trong tests/fixtures/sjc_sample.html
- [ ] Parse: giá mua, giá bán, thời gian update
- [ ] metadata: buy_price, sell_price, sjc_updated_at
- [ ] price = giá bán (giá user thực tế phải trả)
- [ ] ParserError nếu HTML structure không match

## Technical Notes
- SJC update 3 lần/ngày: ~9h, 13h, 16h

## Estimate: ~0.75 day
## Depends on: P3.9-S1
