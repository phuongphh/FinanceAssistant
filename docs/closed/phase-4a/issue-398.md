# Issue #398

[Story] P4A-S24: ContentRenderer port

**Parent Epic:** #374 (Epic 6: Channel-Agnostic Foundation & Polish)

## Description
Protocol interface render_twin_view + Telegram impl + Zalo stub. Architecture doc.

## Acceptance Criteria
- [ ] Protocol in backend/ports/content_renderer.py
- [ ] TelegramContentRenderer passes Twin handler tests
- [ ] Twin handler refactored to use port (not direct telegram_service)
- [ ] Stub ZaloContentRenderer (raises NotImplementedError + TODO)
- [ ] Architecture decision doc: docs/architecture/twin-channel-abstraction.md

## Estimate: ~1 day
## Dependencies: P4A-S14, P4A-S23

Close #374
