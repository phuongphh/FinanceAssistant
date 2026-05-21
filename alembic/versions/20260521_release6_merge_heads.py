"""release 6: merge alembic heads

Release 6 introduced two new revisions that both branched from
``w2r3s4t5u6v7`` (``20260513_expense_enhancement`` and
``x3expense719``) alongside the prod head
``20260518p43expensetrigger``. ``alembic upgrade head`` aborts with
"Multiple head revisions" until a merge revision joins them, so the
deploy needs this no-op merge before prod can advance.

Revision ID: 20260521r6mergeheads
Revises: 20260513_expense_enhancement, 20260518p43expensetrigger, x3expense719
Create Date: 2026-05-21
"""

from __future__ import annotations


revision = "20260521r6mergeheads"
down_revision = (
    "20260513_expense_enhancement",
    "20260518p43expensetrigger",
    "x3expense719",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
