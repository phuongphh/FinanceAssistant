"""Backfill life insurance payment/end date fields.

Revision ID: 20260523_insurance_backfill
Revises: 02940674e911
Create Date: 2026-05-23
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260523_insurance_backfill"
down_revision = "02940674e911"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE assets
        SET extra = jsonb_set(
            jsonb_set(extra, '{monthly_payment_date}', to_jsonb((extra->>'annual_settlement_day')::int), true),
            '{monthly_payment_month}',
            to_jsonb((extra->>'annual_settlement_month')::int),
            true
        )
        WHERE asset_type = 'life_insurance'
          AND extra ? 'annual_settlement_day'
          AND extra ? 'annual_settlement_month'
          AND NOT (extra ? 'monthly_payment_date');
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE assets
        SET extra = (extra - 'monthly_payment_date') - 'monthly_payment_month'
        WHERE asset_type = 'life_insurance'
          AND extra ? 'annual_settlement_day'
          AND extra ? 'annual_settlement_month';
        """
    )
