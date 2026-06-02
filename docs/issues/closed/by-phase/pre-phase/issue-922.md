# Issue #922

default_money_in_source: configurable default income source + money-in confirm UX

## Summary

Mirror the existing `default_expense_source` feature for money-in (income) transactions.

## Requirements

- [ ] Configure a default money-in source (`default_money_in_source`) from the **Profile** main menu, exactly like `default_expense_source`.
- [ ] The default money-in source can only be one of:
  - Tiền mặt (cash)
  - Tài khoản thanh toán [Ngân hàng] (bank payment account)
  - Ví điện tử [Tên ví] (e-wallet)
- [ ] When a money-in transaction is created (via quick transaction **or** via "add money-in transaction from user's query"), the transaction's source is set to `default_money_in_source`.
- [ ] Money-in confirm message mirrors the expense confirm message: a final-confirm UX with **4 inline buttons** allowing the user to edit transaction info. If everything is correct, the user does nothing — the money-in transaction is already created.

## Non-functional

- Consistency with existing system patterns (layer contract, content/*.yaml localization, Decimal money handling).
- Fast response (default applied without extra round-trips).
- UI/UX parity with expense flow; Bé Tiền persona.
- Security / multi-tenancy (`user_id` scoping).

## Tests

- [ ] Unit tests covering config flow, default application on money-in creation, and confirm message + edit buttons.

