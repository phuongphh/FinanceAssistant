# Issue #210

[Story] P3.8-S2: Build RentalService + business logic

**Parent Epic:** #204 (Epic 1: Rental Property Tracking)

## User Story
As a system tracking rentals, I need a RentalService centralized để handle mark-as-rental, occupancy updates, yield aggregation — reusable across UI + agent.

## Acceptance Criteria
- [ ] File `app/wealth/services/rental_service.py` với `RentalService`
- [ ] `mark_as_rental(asset_id, rental_metadata)`:
  - Validate asset_type == "real_estate" (raise ValueError nếu không)
  - Set is_rental=True + store metadata
  - Auto-create `rental` IncomeStream (link với Epic 2)
  - Return updated asset
- [ ] `update_occupancy(asset_id, new_status, effective_date)`:
  - Update occupancy_status
  - "rented" → "vacant": pause linked income stream
  - "vacant" → "rented": resume income stream
- [ ] `unmark_as_rental(asset_id)`:
  - Set is_rental=False + clear metadata
  - Pause linked income streams
- [ ] `get_rental_yield_summary(user_id)`:
  - Returns: property_count, occupied_count, total_monthly_rent, total_monthly_expenses, net_monthly_yield, annual_passive_income
- [ ] Edge cases tested:
  - Mark non-real_estate → ValueError
  - Empty user (no rentals) → return zeros gracefully
  - Non-rental asset occupancy update → no-op or error

## Test Plan
```python
async def test_mark_as_rental():
    asset = await create_real_estate(user, value=2_500_000_000)
    updated = await RentalService().mark_as_rental(asset.id, metadata)
    assert updated.is_rental == True

async def test_yield_summary():
    summary = await RentalService().get_rental_yield_summary(user.id)
    assert summary["net_monthly_yield"] > 0
```

## Estimate: ~1 day
## Depends on: P3.8-S1
