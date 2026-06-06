"""relax wallet provider constraint when source_asset_id pins the wallet

Revision ID: 20260605relaxwalletck
Revises: 20260530defaultmoneyinsource
Create Date: 2026-06-05

Issue #948: tapping an e-wallet asset in the source picker failed with
``IntegrityError`` on ``ck_expenses_wallet_source_consistency`` because
the picker only stores ``source_asset_id`` (the wallet asset row already
identifies the provider) and intentionally leaves ``e_wallet_provider``
NULL. The old constraint required ``e_wallet_provider IS NOT NULL``
whenever ``source_type='e_wallet'``, which contradicts the code path.

This migration relaxes the constraint so the provider column may be
NULL when ``source_asset_id`` is set — the asset row is the source of
truth in that case. The provider column remains required when the
expense is tagged as an e-wallet payment without a linked asset.
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260605relaxwalletck"
down_revision = "20260530defaultmoneyinsource"
branch_labels = None
depends_on = None


_OLD_CONSTRAINT = (
    "(source_type = 'e_wallet' AND e_wallet_provider IS NOT NULL) OR "
    "((source_type IS NULL OR source_type <> 'e_wallet') AND "
    "e_wallet_provider IS NULL)"
)

_NEW_CONSTRAINT = (
    "(source_type = 'e_wallet' AND "
    "(e_wallet_provider IS NOT NULL OR source_asset_id IS NOT NULL)) OR "
    "((source_type IS NULL OR source_type <> 'e_wallet') AND "
    "e_wallet_provider IS NULL)"
)


def upgrade() -> None:
    op.drop_constraint(
        "ck_expenses_wallet_source_consistency", "expenses", type_="check"
    )
    op.create_check_constraint(
        "ck_expenses_wallet_source_consistency",
        "expenses",
        _NEW_CONSTRAINT,
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_expenses_wallet_source_consistency", "expenses", type_="check"
    )
    op.create_check_constraint(
        "ck_expenses_wallet_source_consistency",
        "expenses",
        _OLD_CONSTRAINT,
    )
