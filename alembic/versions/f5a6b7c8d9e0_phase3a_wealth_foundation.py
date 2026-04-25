"""phase 3A — wealth foundation: assets, asset_snapshots, income_streams, user wealth fields

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-04-25 04:30:00.000000

Phase 3A foundation (Issue #59 / P3A-1):

- ``assets`` — user-owned assets (cash, stock, real_estate, crypto, gold,
  other) with JSONB metadata flexible per type. ``initial_value`` and
  ``current_value`` track gain/loss. Soft-delete via ``is_active`` so
  history is preserved when user marks an asset sold.

- ``asset_snapshots`` — daily historical values per asset, source-tagged
  (``user_input`` | ``market_api`` | ``auto_daily`` | ``interpolated``).
  Unique per ``(asset_id, snapshot_date)`` so the daily snapshot job is
  idempotent.

- ``income_streams`` — simple passive/active income tracking for
  threshold-based budgeting and Personal CFO calculations.

- ``users`` extension — wealth-related fields driving the "ladder of
  engagement" (level, thresholds, briefing schedule, currency).

All money columns use ``Numeric(20, 2)`` (assets) or ``Numeric(15, 2)``
(income) — never Float. Indexes target the hot-path queries flagged in
``docs/current/phase-3a-detailed.md`` § 1.1.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f5a6b7c8d9e0'
down_revision: Union[str, Sequence[str], None] = 'e4f5a6b7c8d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- assets -------------------------------------------------------
    op.create_table(
        'assets',
        sa.Column(
            'id', sa.UUID(), nullable=False,
            server_default=sa.text('gen_random_uuid()'),
        ),
        sa.Column('user_id', sa.UUID(), nullable=False),

        # Classification
        sa.Column('asset_type', sa.String(30), nullable=False),
        sa.Column('subtype', sa.String(50), nullable=True),

        # Identity
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),

        # Value tracking (Numeric — never Float for money)
        sa.Column('initial_value', sa.Numeric(20, 2), nullable=False),
        sa.Column('current_value', sa.Numeric(20, 2), nullable=False),
        sa.Column('acquired_at', sa.Date(), nullable=False),
        sa.Column(
            'last_valued_at', sa.DateTime(timezone=True),
            server_default=sa.text('NOW()'), nullable=False,
        ),

        # Flexible per-type metadata
        sa.Column('extra', postgresql.JSONB(), nullable=True),

        # Soft delete / sold tracking
        sa.Column(
            'is_active', sa.Boolean(),
            server_default=sa.text('true'), nullable=False,
        ),
        sa.Column('sold_at', sa.Date(), nullable=True),
        sa.Column('sold_value', sa.Numeric(20, 2), nullable=True),

        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.text('NOW()'), nullable=False,
        ),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True),
            server_default=sa.text('NOW()'), nullable=False,
        ),

        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_assets_user_active', 'assets', ['user_id', 'is_active'])
    op.create_index('idx_assets_type', 'assets', ['asset_type'])

    # --- asset_snapshots ---------------------------------------------
    op.create_table(
        'asset_snapshots',
        sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('asset_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('snapshot_date', sa.Date(), nullable=False),
        sa.Column('value', sa.Numeric(20, 2), nullable=False),
        sa.Column('source', sa.String(20), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.text('NOW()'), nullable=False,
        ),

        sa.ForeignKeyConstraint(['asset_id'], ['assets.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'asset_id', 'snapshot_date',
            name='uq_asset_snapshot_date',
        ),
    )
    op.create_index(
        'idx_snapshots_user_date', 'asset_snapshots',
        ['user_id', 'snapshot_date'],
    )

    # --- income_streams ----------------------------------------------
    op.create_table(
        'income_streams',
        sa.Column(
            'id', sa.UUID(), nullable=False,
            server_default=sa.text('gen_random_uuid()'),
        ),
        sa.Column('user_id', sa.UUID(), nullable=False),

        sa.Column('source_type', sa.String(30), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('amount_monthly', sa.Numeric(15, 2), nullable=False),
        sa.Column(
            'is_active', sa.Boolean(),
            server_default=sa.text('true'), nullable=False,
        ),

        sa.Column('extra', postgresql.JSONB(), nullable=True),

        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.text('NOW()'), nullable=False,
        ),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True),
            server_default=sa.text('NOW()'), nullable=False,
        ),

        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'idx_income_user_active_streams', 'income_streams',
        ['user_id', 'is_active'],
    )

    # --- users: wealth-related extensions -----------------------------
    # Note: ``primary_currency`` is a new field; the existing ``currency``
    # column stays for legacy code paths until Phase 4 cleanup.
    op.add_column(
        'users',
        sa.Column(
            'primary_currency', sa.String(3),
            server_default=sa.text("'VND'"), nullable=False,
        ),
    )
    op.add_column(
        'users',
        sa.Column('wealth_level', sa.String(20), nullable=True),
    )
    op.add_column(
        'users',
        sa.Column(
            'expense_threshold_micro', sa.Integer(),
            server_default=sa.text('200000'), nullable=False,
        ),
    )
    op.add_column(
        'users',
        sa.Column(
            'expense_threshold_major', sa.Integer(),
            server_default=sa.text('2000000'), nullable=False,
        ),
    )
    op.add_column(
        'users',
        sa.Column(
            'briefing_enabled', sa.Boolean(),
            server_default=sa.text('true'), nullable=False,
        ),
    )
    op.add_column(
        'users',
        sa.Column(
            'briefing_time', sa.Time(),
            server_default=sa.text("'07:00:00'"), nullable=False,
        ),
    )
    op.add_column(
        'users',
        sa.Column(
            'onboarding_skipped_asset', sa.Boolean(),
            server_default=sa.text('false'), nullable=False,
        ),
    )
    # Multi-step wizard state (asset entry, etc). JSONB so handlers can
    # stash whatever they need per-step without schema migrations each
    # time we add a wizard. Nullable — most users have no wizard active.
    op.add_column(
        'users',
        sa.Column('wizard_state', postgresql.JSONB(), nullable=True),
    )
    op.create_index('idx_users_wealth_level', 'users', ['wealth_level'])


def downgrade() -> None:
    op.drop_index('idx_users_wealth_level', table_name='users')
    op.drop_column('users', 'wizard_state')
    op.drop_column('users', 'onboarding_skipped_asset')
    op.drop_column('users', 'briefing_time')
    op.drop_column('users', 'briefing_enabled')
    op.drop_column('users', 'expense_threshold_major')
    op.drop_column('users', 'expense_threshold_micro')
    op.drop_column('users', 'wealth_level')
    op.drop_column('users', 'primary_currency')

    op.drop_index('idx_income_user_active_streams', table_name='income_streams')
    op.drop_table('income_streams')

    op.drop_index('idx_snapshots_user_date', table_name='asset_snapshots')
    op.drop_table('asset_snapshots')

    op.drop_index('idx_assets_type', table_name='assets')
    op.drop_index('idx_assets_user_active', table_name='assets')
    op.drop_table('assets')
