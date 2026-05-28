# Issue #884

Migration fails again: revision ID 20260528_default_expense_source_profile exceeds varchar(32)

After fixing `down_revision` in #882, the migration still fails:

```
StringDataRightTruncationError: value too long for type character varying(32)
```

The revision ID `20260528_default_expense_source_profile` is 46 characters, but the `alembic_version.version_num` column is `varchar(32)` (PostgreSQL default created by Alembic). This also caused the auto-merge script to fail.

To reproduce: `alembic upgrade head` on a database that hasn't run any of the new credit-card or expense-source migrations (current version: 0c0010280711).
