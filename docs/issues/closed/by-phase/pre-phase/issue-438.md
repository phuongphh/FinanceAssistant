# Issue #438

[Story] P4B-S21: Zalo Official Account Setup + SDK

**Parent Epic:** #417 (Epic 4: Zalo Adapter Foundation)

## User Story
La developer, toi can Zalo OA client async de gui messages.

## Implementation Tasks
- [ ] adapters/zalo_oa.py: ZaloOAClient with aiohttp
- [ ] send_message, send_image_message methods
- [ ] 429 -> exponential backoff 2s/4s/8s max 3
- [ ] Other errors: log WARNING + return False
- [ ] Env vars: ZALO_OA_ACCESS_TOKEN, ZALO_OA_SECRET_KEY, ZALO_APP_ID

## Estimate: ~1 day
## Depends on: Notifier port (Phase 4A)

Close #417
