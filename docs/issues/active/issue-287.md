# Issue #287

[Story] P3.9-S20: Integration tests end-to-end

**Parent Epic:** #267 (Epic 5: Testing & Polish)

## User Story
As a developer shipping Phase 3.9, I need E2E tests covering entire flow: provider → cache → wealth → briefing.

## Acceptance Criteria
- [x] test_briefing_full_flow: user với 3 stocks + 1 crypto + 1 gold + cash → briefing → all sections present + numbers correct
- [x] test_provider_fallback: mock SSI fail → VNDIRECT used → wealth correct
- [x] test_circuit_breaker: 5 consecutive failures → circuit opens → 5min → half-open
- [x] test_stale_data_flow: provider down → stale data shown with banner
- [x] All tests pass in CI

## Estimate: ~1 day
## Depends on: All Epic 1-4 stories
