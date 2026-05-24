"""credit cards table + expenses.source_credit_card_id link

PR #778 (Issue #774) introduced ``backend.models.credit_card.CreditCard``
(table ``credit_cards``) and a new ``Expense.source_credit_card_id``
column with a FK into it, but shipped without an Alembic migration.
On any deploy that ran ``alembic upgrade head``, the ORM model and the
database schema diverged: every ``select(Expense)`` query emits SQL
referencing ``expenses.source_credit_card_id`` and PostgreSQL replies
with ``UndefinedColumn``. The Mini App expense dashboard's overview
endpoint catches that and returns a generic 500
("Không tải được dữ liệu chi tiêu, thử lại nhé."), which is the symptom
users hit when opening /miniapp/expense.

This migration adds the missing schema in one transaction so prod can
``alembic upgrade head`` and the dashboard recovers. It also extends
``ck_expenses_source_type`` to accept ``'credit_card'`` — without that,
the credit-card source flow inserts would fail the check even once the
column exists.

Revision ID: 20260521creditcards
Revises: 20260521r6mergeheads
Create Date: 2026-05-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260521creditcards"
down_revision = "20260521r6mergeheads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Column types, nullability, and defaults mirror
    # ``backend/models/credit_card.py`` exactly so a subsequent
    # ``alembic revision --autogenerate`` doesn't propose a diff. The
    # model declares Python-side defaults (datetime.utcnow,
    # Decimal("0")) rather than DB server_defaults; we follow suit.
    op.create_table(
        "credit_cards",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("bank_name", sa.String(length=120), nullable=False),
        sa.Column("closing_date", sa.Integer(), nullable=False),
        sa.Column("debt_balance", sa.Numeric(15, 2), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.UniqueConstraint(
            "user_id", "bank_name", name="uq_credit_cards_user_bank_name"
        ),
        # Cheap defence-in-depth on top of the schema validators in
        # ``backend/schemas/credit_card.py`` so direct SQL writes can't
        # poison the table with impossible values.
        sa.CheckConstraint(
            "closing_date BETWEEN 1 AND 31",
            name="ck_credit_cards_closing_date",
        ),
        sa.CheckConstraint(
            "debt_balance >= 0",
            name="ck_credit_cards_debt_balance_non_negative",
        ),
    )
    # ``ix_<table>_<col>`` is the name SQLAlchemy auto-assigns to a
    # column-level ``index=True``. Using the same name here keeps the
    # ORM model and the schema in sync — autogenerate won't propose to
    # rename / recreate it on the next run.
    op.create_index("ix_credit_cards_user_id", "credit_cards", ["user_id"])
    op.create_index(
        "idx_credit_cards_user_created",
        "credit_cards",
        ["user_id", "created_at"],
    )

    op.add_column(
        "expenses",
        sa.Column(
            "source_credit_card_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_expenses_source_credit_card",
        "expenses",
        "credit_cards",
        ["source_credit_card_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # Partial index — most expense rows have no credit-card source, so a
    # full index would waste space. Mirrors the existing
    # ``idx_expenses_source_asset`` pattern.
    op.create_index(
        "idx_expenses_source_credit_card",
        "expenses",
        ["source_credit_card_id"],
        postgresql_where=sa.text("source_credit_card_id IS NOT NULL"),
    )

    # ``ck_expenses_source_type`` from 20260513_expense_enhancement only
    # allows ('cash', 'bank_account', 'e_wallet'). The credit-card source
    # flow inserts ``source_type='credit_card'``, so without widening
    # this constraint the new flow would fail at INSERT time even after
    # the column exists.
    op.drop_constraint("ck_expenses_source_type", "expenses", type_="check")
    op.create_check_constraint(
        "ck_expenses_source_type",
        "expenses",
        "source_type IS NULL OR source_type IN "
        "('cash', 'bank_account', 'e_wallet', 'credit_card')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_expenses_source_type", "expenses", type_="check")
    op.create_check_constraint(
        "ck_expenses_source_type",
        "expenses",
        "source_type IS NULL OR source_type IN ('cash', 'bank_account', 'e_wallet')",
    )

    op.drop_index("idx_expenses_source_credit_card", table_name="expenses")
    op.drop_constraint(
        "fk_expenses_source_credit_card", "expenses", type_="foreignkey"
    )
    op.drop_column("expenses", "source_credit_card_id")

    op.drop_index("idx_credit_cards_user_created", table_name="credit_cards")
    op.drop_index("ix_credit_cards_user_id", table_name="credit_cards")
    op.drop_table("credit_cards")
