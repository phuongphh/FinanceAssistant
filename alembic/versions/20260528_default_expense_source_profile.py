"""add default expense source to user profiles

Revision ID: 20260528_default_expense_source_profile
Revises: 20260527_credit_card_limit_and_debt
Create Date: 2026-05-28
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260528_default_expense_source_profile"
down_revision = "20260527_credit_card_limit_and_debt"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_profiles",
        sa.Column("default_expense_source", sa.String(length=120), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_profiles", "default_expense_source")
