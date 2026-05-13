"""Expense Enhancement transaction source tracking.

Revision ID: 20260513_expense_enhancement
Revises: w2r3s4t5u6v7
Create Date: 2026-05-13
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260513_expense_enhancement"
down_revision = "w2r3s4t5u6v7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "expenses",
        sa.Column(
            "transaction_type",
            sa.String(length=20),
            nullable=False,
            server_default="expense",
        ),
    )
    op.add_column(
        "expenses",
        sa.Column("source_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "expenses", sa.Column("source_type", sa.String(length=30), nullable=True)
    )
    op.add_column(
        "expenses", sa.Column("e_wallet_provider", sa.String(length=30), nullable=True)
    )
    op.create_foreign_key(
        "fk_expenses_source_asset",
        "expenses",
        "assets",
        ["source_asset_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "idx_expenses_type_month",
        "expenses",
        ["user_id", "transaction_type", "month_key"],
    )
    op.create_index(
        "idx_expenses_source_asset",
        "expenses",
        ["source_asset_id"],
        postgresql_where=sa.text("source_asset_id IS NOT NULL"),
    )
    op.create_check_constraint(
        "ck_expenses_transaction_type",
        "expenses",
        "transaction_type IN ('expense', 'money_in')",
    )
    op.create_check_constraint(
        "ck_expenses_source_type",
        "expenses",
        "source_type IS NULL OR source_type IN ('cash', 'bank_account', 'e_wallet')",
    )
    op.create_check_constraint(
        "ck_expenses_e_wallet_provider",
        "expenses",
        "e_wallet_provider IS NULL OR e_wallet_provider IN ('momo', 'vnpay', 'zalopay', 'viettelpay')",
    )
    op.create_check_constraint(
        "ck_expenses_wallet_source_consistency",
        "expenses",
        "(source_type = 'e_wallet' AND e_wallet_provider IS NOT NULL) OR "
        "((source_type IS NULL OR source_type <> 'e_wallet') AND e_wallet_provider IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_expenses_wallet_source_consistency", "expenses", type_="check"
    )
    op.drop_constraint("ck_expenses_e_wallet_provider", "expenses", type_="check")
    op.drop_constraint("ck_expenses_source_type", "expenses", type_="check")
    op.drop_constraint("ck_expenses_transaction_type", "expenses", type_="check")
    op.drop_index("idx_expenses_source_asset", table_name="expenses")
    op.drop_index("idx_expenses_type_month", table_name="expenses")
    op.drop_constraint("fk_expenses_source_asset", "expenses", type_="foreignkey")
    op.drop_column("expenses", "e_wallet_provider")
    op.drop_column("expenses", "source_type")
    op.drop_column("expenses", "source_asset_id")
    op.drop_column("expenses", "transaction_type")
