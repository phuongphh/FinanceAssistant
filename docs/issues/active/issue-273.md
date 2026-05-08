# Issue #273

[Story] P3.9-S6: CoinGecko crypto provider

**Parent Epic:** #264 (Epic 2: Stock + Crypto Providers)

## User Story
As a system, I need CoinGecko free tier integration cho crypto prices.

## Acceptance Criteria
- [ ] `app/market_data/providers/crypto_coingecko.py`
- [ ] Mapping table `coingecko_symbols.py`: BTC→bitcoin, ETH→ethereum, etc. Min 20 cryptos
- [ ] fetch_quote(symbol): lookup mapping → call API → PriceQuote(currency="VND", price=...)
- [ ] fetch_batch: comma-separated IDs trong 1 request
- [ ] Rate limit: 429 → exponential backoff (1s, 2s, 4s) max 3 retries
- [ ] Symbol không trong mapping → SymbolNotFound
- [ ] Unit tests

## Estimate: ~0.5 day
## Depends on: P3.9-S1, P3.9-S2
