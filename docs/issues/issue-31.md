# Issue #31

[Phase 1] Setup Analytics Event Tracking

## User Story
As a product owner, I want to track key user events so that I can understand how users interact with the bot and make data-driven decisions before moving to Phase 2.

## Background
Cross-cutting concern for all of Phase 1. Should be set up in Week 1 and used throughout.

## Tasks
- [ ] Create `app/analytics.py` with `Event` dataclass and `track(event)` function
- [ ] Create `events` table in PostgreSQL (user_id, event_type, properties JSONB, timestamp)
- [ ] Add tracking calls for these events:
  - `bot_started` — user sends /start
  - `transaction_created` — with source (text/voice/image)
  - `button_tapped` — which button (edit, delete, category, undo)
  - `category_changed` — old → new category
  - `transaction_deleted`
  - `miniapp_opened`
  - `miniapp_loaded` — with load_time_ms
- [ ] Create simple admin query to review weekly stats (can be a CLI command or SQL file)

## Acceptance Criteria
- [ ] `track()` saves to PostgreSQL without blocking the main request
- [ ] All 7 event types are tracked in production
- [ ] After 1 week of usage, can answer: which button is tapped most? what is Mini App load time p95?
- [ ] No PII stored in event properties (no message content, no phone numbers)

## Reference
`docs/strategy/phase-1-detailed.md` — Section "Metrics Cần Track"
