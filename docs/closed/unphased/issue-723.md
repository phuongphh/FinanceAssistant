# Issue #723

[Story 4] Edit Transaction with Reverse Logic — Expense Flow

## Summary
Update the "Sửa" (Edit) button for transactions with proper reverse-then-apply logic: reverse old amount first, then apply new amount.

## Requirements
- [ ] When editing a transaction's amount:
  1. **Reverse the old amount** on the source asset:
     - Old outflow (expense): add old amount back to source
     - Old inflow (money-in): subtract old amount from source
  2. **Apply the new amount** on the source asset:
     - New outflow: subtract new amount from source
     - New inflow: add new amount to source
  3. Update the transaction record with new values
  4. Set `edited_at` = NOW()
  5. Link to `original_transaction_id` if it was edited from a previous version
- [ ] When editing non-amount fields (note, category, source_label): no rebalancing needed, just update the record
- [ ] When editing the source asset itself:
  - Reverse old amount from old source
  - Apply new amount to new source
- [ ] Transaction status remains 'active' after edit (it's still a valid transaction, just updated)
- [ ] Keep a copy of the original values before edit (via `original_transaction_id` reference)
- [ ] Edit form pre-fills current transaction values
- [ ] Edge cases:
  - Editing to zero amount: reject with validation error
  - Editing to same amount: no rebalancing needed
  - Editing a reversed transaction: reject (can't edit what's been reversed)

## Acceptance Criteria
- [ ] Edit amount → old amount reversed on source, new amount applied
- [ ] Edit note/category → no rebalancing, just update record
- [ ] Edit source asset → reverse from old source, apply to new source
- [ ] Reversed transactions cannot be edited
- [ ] Original values preserved via `original_transaction_id`
- [ ] Validation: zero amount rejected

## Claude Code Implementation Prompt
```
Read GitHub issue #[ISSUE_NUMBER] in phuongphh/FinanceAssistant.

Implement edit transaction with reverse-then-apply logic:
1. Edit amount: reverse old amount on source, apply new amount
2. Edit note/category: direct update, no rebalancing
3. Edit source: reverse from old source, apply to new source
4. Preserve original values via original_transaction_id
5. Validation edge cases (zero amount, reversed transaction)

Guidelines:
- Branch: improve/edit-transaction-reverse
- Write tests for all edit scenarios
- Conventional commits
- PR closes #[ISSUE_NUMBER]
```

