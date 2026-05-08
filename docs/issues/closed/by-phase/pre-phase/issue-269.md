# Issue #269

[Story] P3.9-S2: Redis price cache layer

**Parent Epic:** #263 (Epic 1: Foundation & Provider Abstraction)

## User Story
As a system, I need cache wrapper với TTL strategy theo asset type và stale-while-revalidate fallback.

## Acceptance Criteria
- [ ] `app/market_data/cache/price_cache.py` với class `PriceCache`
- [ ] Methods: get(key) → PriceQuote, set(quote), set_last_known(quote), get_last_known(symbol), flush_asset_type(type)
- [ ] TTL config: stock=300s, crypto=120s, gold=3600s, bank_rate=604800s, news=1800s
- [ ] Key naming: `market_data:{asset_type}:{symbol}` cho cache, `...:last_known` cho backup (no TTL)
- [ ] get returns None nếu key expired
- [ ] set_last_known luôn ghi đè (last write wins)
- [ ] Dùng `redis.asyncio.Redis`, test với fakeredis

## Estimate: ~1 day
## Depends on: P3.9-S1
