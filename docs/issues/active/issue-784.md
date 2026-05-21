# Issue #784

[Story 1] Life Assurance Data Model & Service

## Summary
Create the life assurance data model and service as a sub-type of Asset. Extend the existing asset model to support life insurance contracts.

## Requirements
- [ ] Extend asset model to support `life_insurance` sub-type:
  - `company_name` (varchar) — tên Công ty bảo hiểm
  - `monthly_payment_date` (int, 1-31) — ngày đóng phí hàng tháng
  - `monthly_amount` (bigint) — số tiền đóng hàng tháng
  - `contract_end_year` (int) — năm tất toán hợp đồng
  - `total_paid` (bigint) — Tổng số tiền đã đóng tính đến hiện tại
- [ ] Service layer:
  - `create_life_insurance(user_id, company_name, monthly_payment_date, monthly_amount, contract_end_year, total_paid?)`
  - `get_life_insurance_list(user_id)` → list all contracts
  - `get_life_insurance_by_id(id)`
  - `update_life_insurance(id, ...)` — update any field
  - `delete_life_insurance(id)` — soft delete
- [ ] Life assurance contracts are counted as assets in net worth calculation
- [ ] `total_paid` auto-calculated on creation if not provided (monthly_amount × months since start)

## Acceptance Criteria
- [ ] Model stores all required fields
- [ ] CRUD operations work correctly
- [ ] Life assurance contracts appear in net worth as assets
- [ ] Auto-calculation of total_paid works
- [ ] Migration rollback-safe

## Claude Code Implementation Prompt
```
Read issue #[ISSUE_NUMBER] in phuongphh/FinanceAssistant.

Create Life Assurance data model + service:
1. Extend asset model with life_insurance sub-type
2. Add all required fields (company_name, monthly_payment_date, monthly_amount, contract_end_year, total_paid)
3. CRUD service layer
4. Auto-calculate total_paid if not provided

Branch: feature/life-assurance-model
PR closes #[ISSUE_NUMBER]
```

