# Issue #276

[Story] P3.9-S9: Wealth valuation integration (stocks + crypto)

**Parent Epic:** #264 (Epic 2: Stock + Crypto Providers)

## User Story
As an end user, I want my portfolio valuation to reflect real market prices — so it shows accurate gain/loss instead of stale user-input prices.

## Acceptance Criteria
- [ ] `app/wealth/valuation/stock.py`: fetch market price via cache (not user_input_price)
- [ ] Giữ user_input_price trong DB (cost basis cho P/L)
- [ ] Add computed field: current_price (read time), pnl_pct = (current_price - cost_basis) / cost_basis * 100
- [ ] Tương tự cho `app/wealth/valuation/crypto.py`
- [ ] Fallback: ProviderUnavailable → log warning, return user_input_price với flag is_stale=True
- [ ] All Phase 3.7+3.8 tests pass (regression)
- [ ] 5 new tests cho fallback + P/L calculation

## Estimate: ~1 day
## Depends on: P3.9-S7, P3.9-S8
