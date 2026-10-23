# Issue #268

[Story] P3.9-S1: Module skeleton + BaseProvider abstract class

**Parent Epic:** #263 (Epic 1: Foundation & Provider Abstraction)

## User Story
As a developer building market data, I need BaseProvider abstract class và module structure để mọi provider có interface chung.

## Acceptance Criteria
- [ ] Folder `app/market_data/` với subfolders: providers/, cache/, jobs/, analytics/
- [ ] `app/market_data/base.py`: abstract class `BaseProvider` với 3 methods: fetch_quote, fetch_batch, asset_type
- [ ] `app/market_data/normalizer.py`: dataclass `PriceQuote` với symbol, price (Decimal), currency, asset_type, fetched_at, source, metadata
- [ ] `app/market_data/exceptions.py`: MarketDataError, ProviderUnavailable, RateLimitError, ParserError, SymbolNotFound, StaleDataWarning
- [ ] Unit tests cho PriceQuote serialization (to_json, from_json)
- [ ] Type hints đầy đủ, mypy clean
- [ ] Decimal (không float) — money rule

## Estimate: ~0.5 day
## Depends on: None
