# Issue #719

[Epic] Enhance Expense Flow — Transaction-based Architecture

## Summary
Migrate expense/money-in recording to a transaction-based architecture. Every expense or money-in is recorded as a transaction in the DB with source, amount, direction (+/-), and note. Enhance Expense Dashboard with reverse and edit capabilities.

## Motivation
Currently expenses and money-ins are recorded as isolated records without proper transaction semantics. This makes it impossible to reverse, edit, or audit financial movements. Moving to a transaction model enables:
- Proper double-entry-like tracking (nguồn tiền → luồng ra/vào)
- Reversible transactions (undo with correct source rebalancing)
- Safe editing (reverse old amount, apply new amount)
- Full audit trail of all money movements

## Issues

### Data Layer
- [#720](https://github.com/phuongphh/FinanceAssistant/issues/720) Transaction Data Model & DB Migration

### Core Logic
- [#721](https://github.com/phuongphh/FinanceAssistant/issues/721) Record Transactions from Expense & Money-In

### Expense Dashboard
- [#722](https://github.com/phuongphh/FinanceAssistant/issues/722) Expense Dashboard — Display Transactions + Reverse Button

### Edit Transaction
- [#723](https://github.com/phuongphh/FinanceAssistant/issues/723) Edit Transaction with Reverse Logic

## Acceptance Criteria
- [ ] All expenses and money-ins are stored as transactions in the DB
- [ ] Each transaction has: source, amount, direction (+/-), note, timestamp, status
- [ ] Expense Dashboard displays transactions with same UI format
- [ ] "Xóa" button replaced with "Reverse" — reverses the amount on the source, then soft-deletes
- [ ] "Sửa" button: reverses old amount, applies new amount, keeps updated transaction
- [ ] All data migrations are rollback-safe
- [ ] 0 P0 regression on existing expense/money-in flows

## Out of Scope
- Recurring transaction generation (already handled elsewhere)
- Multi-currency transactions
- Batch operations

## Claude Code Implementation Prompt
```
Read Epic #719 and all sub-issues (#720-#723) in phuongphh/FinanceAssistant.

Implement transaction-based expense/money-in architecture:
1. Create transaction table with source, amount, direction, note, status, timestamps
2. Record every expense (-) and money-in (+) as a transaction
3. Update Expense Dashboard to display transactions with Reverse button
4. Implement reverse logic: expense → add back to source, money-in → subtract from source, then soft-delete
5. Implement edit with reverse-then-apply pattern

Guidelines:
- Branch: improve/expense-transaction-architecture
- Backward compatible — existing data migration must be safe
- Conventional commits (improve:, feat:)
- Write tests for reverse and edit edge cases
- Create draft PR linking to epic #719
```

