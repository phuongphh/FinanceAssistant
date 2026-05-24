# Issue #721

[Story 2] Record Transactions from Expense & Money-In — Expense Flow

## Summary
Record every expense and money-in as a transaction in the `transactions` table. Expense = outflow (-), money-in = inflow (+).

## Requirements
- [ ] When user records an expense (e.g., "-20k ăn trưa từ tiền mặt"):
  - Create transaction: source="tiền mặt", amount=20000, direction='outflow', note="ăn trưa"
  - Decrease the source asset balance by 20,000
- [ ] When user records a money-in (e.g., "+50k tiền lương"):
  - Create transaction: source="thu nhập (lương)", amount=50000, direction='inflow', note="tiền lương"
  - Increase the source asset balance by 50,000
- [ ] Both legacy (via backfill) and new flows write to `transactions`
- [ ] All existing APIs that record expense/money-in must also create a transaction record
- [ ] No data loss: existing expense and money-in tables continue to work alongside transactions (dual-write during migration)
- [ ] After migration verification, new code reads from `transactions` instead of legacy tables

## Acceptance Criteria
- [ ] "-20k ăn trưa từ tiền mặt" → transaction created with direction='outflow', amount=20000, note="ăn trưa"
- [ ] "+50k tiền lương" → transaction created with direction='inflow', amount=50000, note="tiền lương"
- [ ] Source asset balance updated correctly in both cases
- [ ] Dual-write during migration period — no data loss
- [ ] Legacy expense/money-in tables remain for rollback

## Claude Code Implementation Prompt
```
Read GitHub issue #[ISSUE_NUMBER] in phuongphh/FinanceAssistant.

Implement transaction recording for expense and money-in:
1. When expense recorded → create transaction (outflow) + decrease source asset
2. When money-in recorded → create transaction (inflow) + increase source asset
3. Dual-write during migration (write to both legacy and new tables)
4. After verified, switch reads to transactions table

Guidelines:
- Branch: improve/record-transactions
- Dual-write safe — no data loss on failure
- Write tests for both expense and money-in paths
- Conventional commits
- PR closes #[ISSUE_NUMBER]
```

