# Issue #948

Expense source: e_wallet missing e_wallet_provider (CheckViolation) + amount parse error

When selecting a wallet provider as the expense source, the update fails with:

```
sqlalchemy.exc.IntegrityError: new row for relation "expenses" violates check constraint "ck_expenses_wallet_source_consistency"
```

The check constraint requires:
- If `source_type = e_wallet` → `e_wallet_provider IS NOT NULL`
- If `source_type != e_wallet` or NULL → `e_wallet_provider IS NULL`

The failing row shows `source_type = e_wallet` but `e_wallet_provider` is null (user: 9c199f69).

Additionally, the same transaction shows amount `199000000000000 VND` (description: `-199tỷ`) — an amount parse error, likely from input like `199k` or similar.
