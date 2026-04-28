"""phase B5 — composite partial indexes for hot-path queries

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-04-23 06:00:00.000000

Adds three partial indexes backing the queries the service layer runs
on every report / dashboard / morning-push:

- ``goals(user_id, is_active)`` where ``deleted_at IS NULL`` — hot path
  for ``goal_service.list_active`` and morning-report goal snapshot.
- ``income_records(user_id)`` where ``deleted_at IS NULL`` — hot path
  for ``income_service.list_active`` and report income rollup.
- ``expenses(user_id, month_key, category)`` where ``deleted_at IS NULL``
  — hot path for monthly-report breakdown.

All use partial indexes to skip soft-deleted rows (20-30% size saving
once soft-deletes accumulate) and ``CREATE INDEX CONCURRENTLY`` so the
migration doesn't take a table-level lock on write-heavy tables at the
size we'll be at in Phase 1 VPS.

Rationale: docs/archive/scaling-refactor-B.md §B5.
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'e4f5a6b7c8d9'
down_revision: Union[str, Sequence[str], None] = 'd3e4f5a6b7c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# CREATE INDEX CONCURRENTLY cannot run inside a transaction block, so
# each index is issued in its own autocommit block. ``IF NOT EXISTS``
# keeps re-runs safe in case a previous attempt failed mid-way.

def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_goals_user_active "
            "ON goals (user_id, is_active) "
            "WHERE deleted_at IS NULL"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_income_user_active "
            "ON income_records (user_id) "
            "WHERE deleted_at IS NULL"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_expenses_user_month_cat "
            "ON expenses (user_id, month_key, category) "
            "WHERE deleted_at IS NULL"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_expenses_user_month_cat")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_income_user_active")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_goals_user_active")
