# Issue #116

[Story] P3.5-S3: Build parameter extractors (time, category, ticker, amount)

**Parent Epic:** #110 (Epic 1: Intent Foundation & Patterns)

## User Story
As an intent classifier, I need helper functions để extract structured parameters (time ranges, categories, tickers, amounts) từ raw Vietnamese text, so downstream handlers receive clean typed data.

## Acceptance Criteria

### Time Range Extractor (`app/intent/extractors/time_range.py`)
- [ ] Returns `TimeRange(start, end, label)` dataclass
- [ ] Nhận biết: hôm nay, hôm qua, tuần này, tuần trước/qua, tháng này, tháng trước/qua, năm nay
- [ ] Returns None khi không tìm thấy
- [ ] Edge: tháng 1 → tháng trước = tháng 12 năm trước

### Category Extractor (`app/intent/extractors/category.py`)
- [ ] Returns category code ("food", "health",...) hoặc None
- [ ] Map Vietnamese keywords cho 10 categories
- [ ] Mỗi category có 5+ keyword variations

### Ticker Extractor (`app/intent/extractors/ticker.py`)
- [ ] **Whitelist-based:** chỉ return known VN30 tickers + crypto + ETFs
- [ ] Handle "VN-Index", "vnindex" → "VNINDEX"
- [ ] Handle "bitcoin" → "BTC", "ethereum" → "ETH"

### Amount Extractor (`app/intent/extractors/amount.py`)
- [ ] "1tr"=1000000, "500k"=500000, "2 triệu"=2000000, "1.5 tỷ"=1500000000
- [ ] Handle plain numbers ≥1000
- [ ] Returns None cho ambiguous "5" hoặc "10"

- [ ] Unit tests >90% coverage cho mỗi extractor
- [ ] Mỗi extractor: chỉ nhận `text: str` (stateless)

## Estimate: ~1 day
## Depends on: P3.5-S1
## Reference: `docs/current/phase-3.5-detailed.md` § 1.3
