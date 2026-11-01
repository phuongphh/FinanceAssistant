# Issue #720

[Story 1] Transaction Data Model & DB Migration — Expense Flow

## Summary
Create the `transactions` table to store every expense and money-in as a transaction with source, amount, direction, note, and status fields.

## Requirements
- [ ] Create `transactions` table with columns:
  - `id` (UUID, PK)
  - `user_id` (FK → users)
  - `source_asset_id` (FK → assets, nullable) — nguồn tiền (tiền mặt, tài khoản ngân hàng, etc.)
  - `source_type` (enum: 'cash', 'bank', 'income', 'expense_category') — loại nguồn
  - `source_label` (varchar) — tên hiển thị của nguồn (e.g., "tiền mặt", "lương", "ăn trưa")
  - `amount` (bigint) — số tiền (luôn dương, direction quyết định +/-)
  - `direction` (enum: 'inflow', 'outflow') — '+' cho money-in, '-' cho expense
  - `note` (text) — ghi chú (e.g., "ăn trưa", "tiền lương")
  - `category` (varchar, nullable) — danh mục
  - `status` (enum: 'active', 'reversed', 'edited') — trạng thái
  - `reversed_at` (timestamptz, nullable) — thời điểm reverse
  - `reversed_by_transaction_id` (UUID, nullable, self-ref FK) — transaction đã reverse nó
  - `edited_at` (timestamptz, nullable)
  - `original_transaction_id` (UUID, nullable, self-ref FK) — transaction gốc nếu là bản edited
  - `created_at`, `updated_at` (timestamptz)
- [ ] Migration script rollback-safe (DROP TABLE IF EXISTS ... CASCADE)
- [ ] Index on (user_id, created_at DESC) for dashboard queries
- [ ] Index on (status) for active/reversed filtering
- [ ] Backfill migration: chuyển expenses và money-ins hiện tại thành transactions với flag `is_backfilled = true`
- [ ] Add `is_backfilled` column để phân biệt data cũ vs mới

## Acceptance Criteria
- [ ] Table created with all columns above
- [ ] Migration runs cleanly on dev/staging/production
- [ ] Rollback works correctly
- [ ] Indexes in place for query performance
- [ ] Backfill migration preserves all existing data

## Claude Code Implementation Prompt
```
Read GitHub issue #[ISSUE_NUMBER] in phuongphh/FinanceAssistant.

Create transaction data model:
1. Create `transactions` table with all specified columns
2. Create enums for direction, status, source_type
3. Add indexes
4. Write backfill migration for existing expenses and money-ins
5. Ensure rollback safety

Guidelines:
- Branch: improve/transaction-data-model
- All migrations must be rollback-safe
- Write tests for the model
- Conventional commits
- PR closes #[ISSUE_NUMBER]
```

