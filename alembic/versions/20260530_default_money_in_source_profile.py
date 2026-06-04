"""add default money-in source to user profiles

Revision ID: 20260530defaultmoneyinsource
Revises: 20260529salutation
Create Date: 2026-05-30
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260530defaultmoneyinsource"
down_revision = "20260529salutation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_profiles",
        sa.Column("default_money_in_source", sa.String(length=120), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_profiles", "default_money_in_source")
