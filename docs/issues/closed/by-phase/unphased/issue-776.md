# Issue #776

[Story 2] Expense Transaction with Credit Card Source

## Summary
Allow expense transactions to select a credit card as the source. When an expense is charged to a credit card, increase the card's debt balance instead of decreasing cash/bank assets.

## Requirements
- [ ] NLU updates: detect "trả bằng thẻ [bank]" or "bằng thẻ [bank]" in expense queries
- [ ] If credit card found for [bank] name → source = credit card, NOT cash/bank account
- [ ] Expense transaction logic for credit card source:
  - Create transaction: source=credit_card_[bank], amount=X, direction='outflow', note="..."
  - **Increase** credit card debt_balance by the expense amount
  - Do NOT deduct from cash/bank assets
- [ ] Example 1: "-200k mua quần áo trả bằng thẻ UOB"
  → Find credit card "UOB", increase debt by 200k, transaction note="mua quần áo"
- [ ] Example 2: "-230k trả tiền Claude bằng thẻ tín dụng MSB"
  → Find credit card "MSB", increase debt by 230k, transaction note="trả tiền Claude"
- [ ] If credit card not found for [bank] → fallback to normal expense flow
- [ ] Credit card debt_balance should appear in net worth calculation (as liability)

## Acceptance Criteria
- [ ] "-200k mua quần áo trả bằng thẻ UOB" → UOB debt +200k
- [ ] "-230k trả tiền Claude bằng thẻ MSB" → MSB debt +230k
- [ ] Cash/bank assets NOT affected when credit card source used
- [ ] Fallback to normal expense if card not found
- [ ] NLU parses "trả bằng thẻ [bank]" and "bằng thẻ [bank]" patterns

## Claude Code Implementation Prompt
```
Read issue #[ISSUE_NUMBER] in phuongphh/FinanceAssistant.

Allow expense transactions to source from credit cards:
1. NLU: detect "trả bằng thẻ [bank]" / "bằng thẻ [bank]" patterns
2. If matching credit card found → increase debt_balance, don't deduct cash
3. Fallback to normal expense if card not found
4. Include credit card debt in net worth as liability

Branch: feature/credit-card-expense
PR closes #[ISSUE_NUMBER]
```

