# Issue #775

[Story 1] Create & Manage Credit Cards — Data Model + CRUD

## Summary
Create the credit card data model and CRUD operations. Users can create new credit cards with bank name (unique per user), monthly closing date, and debt balance.

## Requirements
- [ ] Create `credit_cards` table:
  - `id` (UUID, PK)
  - `user_id` (FK → users)
  - `bank_name` (varchar, unique per user) — tên ngân hàng
  - `closing_date` (int, 1-31) — ngày tất toán hàng tháng
  - `debt_balance` (bigint, default 0) — số dư nợ hiện tại
  - `created_at`, `updated_at` (timestamptz)
- [ ] Unique constraint on (user_id, bank_name) — check when creating:
  - If bank_name already exists for this user → reject with message "Thẻ [bank] đã tồn tại"
- [ ] Create credit card command: `/tao_the_tin_dung [bank_name] [closing_date] [debt_balance?]`
- [ ] List credit cards command/user flow
- [ ] Edit credit card (change closing date, rename bank)
- [ ] Soft-delete credit card (set status='deleted')

## Acceptance Criteria
- [ ] Table created with all columns
- [ ] Unique (user_id, bank_name) constraint works
- [ ] Creating duplicate bank name → rejected with clear message
- [ ] CRUD operations work correctly
- [ ] Migration rollback-safe

## Claude Code Implementation Prompt
```
Read issue #[ISSUE_NUMBER] in phuongphh/FinanceAssistant.

Implement credit card data model + CRUD:
1. Create credit_cards table (id, user_id, bank_name, closing_date, debt_balance, timestamps)
2. Unique constraint on (user_id, bank_name)
3. CRUD operations with bank name uniqueness validation
4. Migration script

Branch: feature/credit-card-model
PR closes #[ISSUE_NUMBER]
```

