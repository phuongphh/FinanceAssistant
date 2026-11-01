# Issue #563

[Story] US1: Transaction model — extend with source, type, linked asset

**Parent Epic:** #562 (Expense Enhancement)

Mo rong transaction model de ho tro 2 loai (expense/money_in) + gan nguon.

## Acceptance Criteria
- [ ] Them field `transaction_type` enum: expense | money_in
- [ ] Them field `source_asset_id` FK to assets table (tien mat, tai khoan, vi)
- [ ] Them field `source_type` enum: cash | bank_account | e_wallet
- [ ] Them field `e_wallet_provider` neu source_type=e_wallet (momo, vnpay, zalopay, viettelpay)
- [ ] Migration them columns, backfill existing transactions
- [ ] Khi transaction la expense: tru di source_asset.current_value
- [ ] Khi transaction la money_in: cong vao source_asset.current_value
- [ ] Transaction khong co source -> van hoat dong nhu cu (backward compatible)

Close #562
