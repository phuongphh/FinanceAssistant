# Issue #722

[Story 3] Expense Dashboard — Display Transactions + Reverse Button — Expense Flow

## Summary
Update Expense Dashboard to display transactions instead of raw expenses, replace "Xóa" button with "Reverse" that reverses the transaction and rebalances the source.

## Requirements
- [ ] Expense Dashboard displays transactions (both expenses and money-ins)
- [ ] Keep same UI/format as current dashboard — no visual changes
- [ ] Expense (outflow) shown in red/expense color, Money-in (inflow) shown in green/income color
- [ ] **Replace "Xóa" button → "Reverse" button** with the following logic:
  - If transaction is expense (outflow): **cộng lại** số amount vào nguồn (add back)
  - If transaction is money-in (inflow): **trừ đi** số amount ở nguồn (subtract)
  - Set transaction status to 'reversed'
  - Set `reversed_at` to NOW()
  - Set `reversed_by_transaction_id` — optionally create a compensating transaction
  - Soft delete: transaction stays in DB but hidden from default dashboard view
- [ ] Reverse action requires confirmation: "Bạn có chắc muốn đảo ngược giao dịch này?"
- [ ] Reversed transactions are filterable (show/hide reversed toggle)
- [ ] Backward compatible: old expense records without transactions still display correctly

## Acceptance Criteria
- [ ] Dashboard shows both expenses and money-ins as transactions
- [ ] UI format unchanged from current dashboard
- [ ] "Xóa" button replaced with "Reverse" with correct label and icon
- [ ] Reverse expense → amount added back to source, transaction soft-deleted
- [ ] Reverse money-in → amount subtracted from source, transaction soft-deleted
- [ ] Confirmation dialog before reverse
- [ ] Reversed transactions hidden by default, toggle to show

## Claude Code Implementation Prompt
```
Read GitHub issue #[ISSUE_NUMBER] in phuongphh/FinanceAssistant.

Update Expense Dashboard:
1. Display transactions (expenses + money-ins) in same UI format
2. Replace "Xóa" button with "Reverse" button
3. Reverse logic: expense → add back to source, money-in → subtract from source
4. Soft delete (set status='reversed')
5. Confirmation dialog
6. Toggle to show/hide reversed transactions

Guidelines:
- Branch: improve/expense-dashboard-reverse
- Keep existing UI unchanged
- Write tests for reverse logic edge cases
- Conventional commits
- PR closes #[ISSUE_NUMBER]
```

