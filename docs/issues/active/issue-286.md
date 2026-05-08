# Issue #286

[Story] P3.9-S19: Replace Phase 3.7 stubs in agent tools

**Parent Epic:** #266 (Epic 4: Enhanced Briefing + Analytics + Alerts)

## User Story
As a system, I need agent tools (Phase 3.7) to use real market data instead of stub.

## Acceptance Criteria
- [ ] `app/agent/tools/market_query.py` updated: gọi market_data functions
- [ ] Tool description updated: bỏ "stub data" warning
- [ ] All Phase 3.7 agent tests pass
- [ ] 5 test queries (manual):
  - "VN-Index hôm nay?"
  - "BTC giá bao nhiêu?"
  - "vàng SJC?"
  - "lãi suất Vietcombank?"
  - "tin gì về HPG?"
- [ ] Tool call latency P95 < 500ms (cache hit)

## Estimate: ~0.5 day
## Depends on: P3.9-S9, P3.9-S12, P3.9-S13, P3.9-S15
