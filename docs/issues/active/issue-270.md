# Issue #270

[Story] P3.9-S3: Provider dispatcher + circuit breaker

**Parent Epic:** #263 (Epic 1: Foundation & Provider Abstraction)

## User Story
As a system, I need fallback logic (primary → secondary) và circuit breaker để tránh hammer provider đang down.

## Acceptance Criteria
- [ ] `app/market_data/providers/base_dispatcher.py` với class `Dispatcher(primary, secondary, timeout=3.0)`
- [ ] fetch_quote(symbol): try primary với timeout, catch (TimeoutError, ProviderUnavailable, RateLimitError), fallback secondary
- [ ] Circuit breaker: count consecutive failures per provider trong Redis
- [ ] ≥5 failures trong 60s → open circuit 5 phút (key `market_data:health:{provider}:open_until`)
- [ ] Open → skip primary, đi thẳng secondary
- [ ] 5 phút sau → half-open: 1 request thử → success reset, fail mở lại 5 phút
- [ ] Unit tests: closed, open, half-open states
- [ ] Log mọi state transition

## Estimate: ~1 day
## Depends on: P3.9-S2
