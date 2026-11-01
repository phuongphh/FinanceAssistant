# Issue #882

Migration fails: 20260528_default_expense_source_profile references wrong down_revision

When running `alembic upgrade head` after deploying commit 27520eb..50d577c, the migration fails with:

```
KeyError: '20260527_credit_card_limit_and_debt'
```

The new migration `20260528_default_expense_source_profile.py` sets `down_revision = 20260527_credit_card_limit_and_debt` but the actual revision ID inside `20260527_credit_card_limit_and_debt.py` is `20260527creditlimit`.

This causes Alembic to reject the revision chain and the deploy script exits before the backend can restart.
