# Issue #271

[Story] P3.9-S4: SSI iBoard stock provider (primary)

**Parent Epic:** #264 (Epic 2: Stock + Crypto Providers)

## User Story
As a system, I need SSI iBoard API client cho real-time stock quotes.

## Acceptance Criteria
- [ ] `app/market_data/providers/stock_ssi.py` với class `SSIStockProvider(BaseProvider)`
- [ ] fetch_quote(symbol) gọi SSI endpoint, parse → PriceQuote
- [ ] fetch_batch(symbols) dùng batch endpoint hoặc concurrent calls với asyncio.gather
- [ ] metadata: volume, change_pct, high, low, open
- [ ] Error handling: 4xx → SymbolNotFound/ProviderUnavailable, 5xx → ProviderUnavailable, 429 → RateLimitError
- [ ] Timeout 3s (configurable)
- [ ] httpx.AsyncClient
- [ ] Unit tests (4 cases: success, 404, 500, 429)
- [ ] Integration test 1 symbol thật (manual, không CI)

## Estimate: ~1 day
## Depends on: P3.9-S1, P3.9-S2
