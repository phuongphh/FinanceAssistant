# Issue #423

[Story] P4B-S6: Life Event Data Model + Migration

**Parent Epic:** #415 (Epic 2: Life Event Simulator)

## User Story
Là developer, tôi cần DB schema và Pydantic models để lưu life events.

## Implementation Tasks
- [ ] Alembic migration: create table life_events per schema
- [ ] Pydantic: LifeEventCreate, LifeEventRead, LifeEventUpdate, LifeEventImpact
- [ ] LifeEventType enum (6 values: buy_house, marry, first_child, education, car, savings)
- [ ] life_event_service.py: create, get_by_user, update, soft_delete
- [ ] Soft delete via deleted_at

## Estimate: ~0.5 day
## Dependencies: None

Close #415
