"""fix transactions.amount: BIGINT -> NUMERIC(20, 2)

Issue #801 — money-in > 2.1 tỷ VND failed with asyncpg
``value out of range``. Root cause: the ``Transaction.amount`` ORM
attribute was declared ``Mapped[int]``, which SQLAlchemy compiles to
``Integer`` for parameter binding. asyncpg then validated bind values
against the INT4 range even though the underlying column was created as
BIGINT. CLAUDE.md mandates ``NUMERIC(20, 2)`` for money columns; this
migration aligns the database with the convention used by
``expenses.amount`` so that schema, model, and bind types all agree.

The conversion is lossless: BIGINT values fit comfortably inside
NUMERIC(20, 2).

Revision ID: 20260522fixtxamt
Revises: 20260521creditcards
Create Date: 2026-05-22
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260522fixtxamt"
down_revision = "20260521creditcards"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "transactions",
        "amount",
        type_=sa.Numeric(20, 2),
        existing_type=sa.BigInteger(),
        existing_nullable=False,
        postgresql_using="amount::numeric(20,2)",
    )


def downgrade() -> None:
    op.alter_column(
        "transactions",
        "amount",
        type_=sa.BigInteger(),
        existing_type=sa.Numeric(20, 2),
        existing_nullable=False,
        postgresql_using="amount::bigint",
    )
