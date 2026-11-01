# Issue #887

rebuild-finance.sh: alembic upgrade head wrapped in single string

Line 76 of `rebuild-finance.sh` has:

```bash
"$PROJECT_DIR/.venv/bin/alembic upgrade head" 2>&1 | tee -a "$LOG_FILE"
```

The entire `alembic upgrade head` is quoted as a single path string, so the shell tries to execute `/path/to/.venv/bin/alembic upgrade head` (with spaces) as a filename, failing with:

```
/PATH/FinanceAssistant/.venv/bin/alembic upgrade head: No such file or directory
```

Fix: remove the outer quotes so the arguments are passed separately.

