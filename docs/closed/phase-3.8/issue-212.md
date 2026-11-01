# Issue #212

[Story] P3.8-S4: IncomeStream model + service

**Parent Epic:** #205 (Epic 2: Multi-Income Streams)

## User Story
As a system tracking multi-income, I need IncomeStream model với 6 types và IncomeService cho CRUD + normalization to monthly.

## Acceptance Criteria
- [ ] Migration tạo bảng `income_streams` với: id, user_id, income_type, name, amount, currency, schedule, day_of_month, month_of_year, start_date, end_date, is_active, source_asset_id, metadata
- [ ] Model `IncomeStream` đầy đủ fields
- [ ] Service `IncomeService` với methods:
  - `add_income_stream(user_id, stream_data)`
  - `update_income_stream(stream_id, updates)`
  - `pause_stream(stream_id)` / `resume_stream(stream_id)`
  - `get_active_streams(user_id)`
  - `get_total_monthly_income(user_id)` → dict: total, active, passive, ratio, count
- [ ] Helper `_normalize_to_monthly(stream)`:
  - monthly → as-is
  - quarterly → amount / 3
  - annually → amount / 12
  - ad_hoc → average over last 6 months (fallback: amount/6)
- [ ] **Income types từ YAML** (`content/income_types.yaml`):
  - 6 types: salary, freelance, dividend, rental, interest, other
  - Mỗi type có: label_vi, is_passive, typical_schedule, icon
- [ ] **Test:** salary 30tr/tháng + dividend 10tr/năm → total monthly ≈ 30.83tr

## Estimate: ~1 day
## Depends on: None (parallel với Epic 1 + 3)
