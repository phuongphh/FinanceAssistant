# Issue #381

[Story] P4A-S7: Migration twin_projections table

**Parent Epic:** #370 (Epic 2: Persistence & Scheduler)

## Description
Alembic migration cho table twin_projections với JSONB cone data.

## Acceptance Criteria
- [ ] File: alembic/versions/xxx_phase4a_twin_projections.py
- [ ] Schema match detailed.md § Database Schema
- [ ] Indexes: idx_twin_proj_user_latest, idx_twin_proj_user_scenario
- [ ] alembic upgrade head clean
- [ ] alembic downgrade -1 reversible

## Estimate: ~0.5 day
## Dependencies: None

Close #370
