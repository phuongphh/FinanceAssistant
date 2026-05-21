# Issue #774

[Epic] Credit Card Management — Create, Expense, Menu

## Summary
Add Credit Card management to Finance Assistant: allow users to create credit cards, track debt, and record expenses charged to specific cards.

## Motivation
Users need to track credit card debt alongside their other assets and expenses. Currently, expenses can only be sourced from cash/bank accounts. Adding credit card support enables complete financial tracking — users can record credit card spending and monitor their outstanding balance and closing dates.

## Issues
- [#775](https://github.com/phuongphh/FinanceAssistant/issues/775) Create & Manage Credit Cards (data model + CRUD)
- [#776](https://github.com/phuongphh/FinanceAssistant/issues/776) Expense Transaction with Credit Card Source
- [#777](https://github.com/phuongphh/FinanceAssistant/issues/777) Credit Card Menu in Chi Tiêu

## Acceptance Criteria
- [ ] User can create a credit card with bank name (unique), closing date, debt balance
- [ ] Bank name uniqueness validated per user
- [ ] Expense can select a credit card as source → debt balance increases
- [ ] Bé Tiền NLU parses "trả bằng thẻ [bank]" correctly
- [ ] "Thẻ tín dụng" button in Chi tiêu main menu
- [ ] Menu lists all cards with debt balance + closing date
- [ ] Foot buttons: "Quản lý thẻ tín dụng" + "Quay về"
- [ ] 0 P0 regression on existing expense flows

## Out of Scope
- Credit card payment/reconciliation (paying off card debt)
- Credit card rewards/cashback tracking
- Multiple currencies

## Claude Code Implementation Prompt
```
Read Epic #774 and all sub-issues (#775-#777) in phuongphh/FinanceAssistant.

Implement Credit Card management:
1. Create credit_cards table + CRUD (bank name unique per user, closing date, debt balance)
2. Allow expense transactions to source from credit card → increase debt balance
3. Add "Thẻ tín dụng" button in Chi tiêu menu with card list view

Guidelines:
- Branch: feature/credit-card-management
- NLU must handle "trả bằng thẻ [bank]" patterns
- Conventional commits (feat:)
- Write tests for CRUD + expense with credit card source
- Create draft PR linking to epic #774
```

