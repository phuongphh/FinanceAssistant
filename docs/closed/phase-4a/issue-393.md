# Issue #393

[Story] P4A-S19: REST API endpoint GET /api/twin

**Parent Epic:** #372 (Epic 4: Mini App Basic Twin Dashboard)

## Description
JSON projection endpoint. Auth via Telegram WebApp initData HMAC.

## Acceptance Criteria
- [ ] GET /api/twin?scenario=current returns projection JSON
- [ ] initData HMAC validated với bot token
- [ ] 401 on invalid initData
- [ ] ETag based on computed_at, 304 on match
- [ ] No business logic in route (thin → service)
- [ ] Integration test: valid + invalid initData

## Estimate: ~0.5 day
## Dependencies: P4A-S11

Close #372
