# Issue #209

[Story] P3.8-S1: Extend Asset model with rental fields

**Parent Epic:** #204 (Epic 1: Rental Property Tracking)

## User Story
As a developer extending wealth tracking, I need `is_rental` boolean và `rental_metadata` JSON trong Asset model để real_estate assets carry rental-specific data mà không affect other asset types.

## Acceptance Criteria
- [ ] Migration adds `is_rental` (Boolean, default=False, nullable=False) vào assets table
- [ ] Migration adds `rental_metadata` (JSON, nullable=True) vào assets table
- [ ] Pydantic schema `RentalMetadata`:
  - monthly_rent (Decimal)
  - occupancy_status (Literal: "rented" | "vacant" | "self_use")
  - tenant_name (Optional str)
  - lease_start_date / lease_end_date (Optional date)
  - monthly_expenses (Decimal, default=0)
  - deposit_held (Decimal, default=0)
- [ ] Computed properties:
  - `net_monthly_yield` = rent - expenses
  - `annual_yield_pct(property_value)` = annual net / value × 100
- [ ] Tất cả existing tests pass sau migration
- [ ] `is_rental` default False → existing assets không bị ảnh hưởng
- [ ] `downgrade()` hoạt động

## Estimate: ~0.5 day
## Depends on: None
## Reference: `docs/current/phase-3.8/phase-3.8-detailed.md` § 1.1
