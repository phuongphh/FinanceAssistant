"""add credit_limit to credit_cards

Revision ID: 20260527creditlimit
Revises: 20260521creditcards
Create Date: 2026-05-27
"""
from alembic import op
import sqlalchemy as sa

revision = "20260527creditlimit"
down_revision = "20260521creditcards"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("credit_cards", sa.Column("credit_limit", sa.Numeric(15, 2), nullable=True))
    op.execute("UPDATE credit_cards SET credit_limit = debt_balance WHERE credit_limit IS NULL")
    op.alter_column("credit_cards", "credit_limit", nullable=False)
    op.create_check_constraint(
        "ck_credit_cards_credit_limit_non_negative",
        "credit_cards",
        "credit_limit >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_credit_cards_credit_limit_non_negative", "credit_cards", type_="check")
    op.drop_column("credit_cards", "credit_limit")
