# Issue #901

Fix funding-source balance adjustment on edit/reverse + deterministic "latest" ordering

## Summary

Audit and fix transaction balance logic across all four funding-source types and ensure "latest transaction / latest asset" lookups are unambiguous.

### Problem 1 — Credit-card debt ignored transaction direction (correctness bug)

`expense_service._adjust_source_asset` adjusted credit-card `debt_balance` by `amount * multiplier`, **ignoring the transaction direction**. This meant a `money_in` event (refund / repayment) on a credit card wrongly **increased** the debt instead of lowering it. The asset branch (cash / bank / e-wallet) already honoured direction via `_source_asset_delta`; the credit-card branch did not. The card row was also not locked (`SELECT … FOR UPDATE`), unlike the asset branch, leaving a race window on concurrent edit/reverse.

Both edit entry points — the Expense Dashboard miniapp (`PATCH /miniapp/api/expenses/{id}`) and Telegram message edits — funnel through `expense_service.update_expense` / `delete_expense`, so this single fix covers both surfaces for **Cash (Tiền mặt)**, **Ví điện tử**, **Thẻ tín dụng** (số dư nợ), and **Tài khoản thanh toán**.

### Problem 2 — Ambiguous "latest" lookups

`list_expenses` ordered by `expense_date` (day precision) only, and `list_incomes` by `period` (day precision) only — two rows on the same day tied non-deterministically, so "most-recent transaction" lookups were unreliable. Underlying timestamp columns are already `DateTime(timezone=True)` (second precision); the gap was purely in the ORDER BY.

## Requirements

- [x] Credit-card debt adjustment honours direction on edit and reverse (expense → debt +amount, money_in → debt −amount)
- [x] Credit-card row locked with `SELECT … FOR UPDATE` like the asset branch
- [x] Cash / bank / e-wallet balance verified correct on edit and reverse (centralized)
- [x] `list_expenses` ordering: `expense_date DESC, created_at DESC, id DESC`
- [x] `list_incomes` ordering: `period DESC, created_at DESC, id DESC`
- [x] Asset listing tie-broken by `id` so latest-asset lookup is deterministic
- [x] Full unit tests for all four source types across edit/reverse, including the credit-card money_in regression case

## Acceptance Criteria

- [x] Credit-card money_in lowers debt; expense raises it; reverse restores prior balance
- [x] No `db.commit()` added to service layer (layer contract preserved)
- [x] "Latest transaction" / "latest asset" lookups are deterministic
- [x] Tests green, lint clean
