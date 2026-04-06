"""add portfolio_assets and income_records tables

Revision ID: a1b2c3d4e5f6
Revises: 4af8805c9efd
Create Date: 2026-04-06 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '4af8805c9efd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create portfolio_assets and income_records tables."""
    op.create_table(
        'portfolio_assets',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('asset_type', sa.String(30), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('quantity', sa.Numeric(20, 6), nullable=True),
        sa.Column('purchase_price', sa.Numeric(15, 0), nullable=True),
        sa.Column('current_price', sa.Numeric(15, 0), nullable=True),
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_portfolio_assets_user_id', 'portfolio_assets', ['user_id'])
    op.create_index('idx_portfolio_user_type', 'portfolio_assets', ['user_id', 'asset_type'])

    op.create_table(
        'income_records',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('income_type', sa.String(20), nullable=False),
        sa.Column('source', sa.String(50), nullable=False),
        sa.Column('asset_id', sa.UUID(), nullable=True),
        sa.Column('amount', sa.Numeric(15, 0), nullable=False),
        sa.Column('period', sa.Date(), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['asset_id'], ['portfolio_assets.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_income_records_user_id', 'income_records', ['user_id'])
    op.create_index('idx_income_user_period', 'income_records', ['user_id', 'period'])
    op.create_index('idx_income_user_type', 'income_records', ['user_id', 'income_type'])


def downgrade() -> None:
    """Drop portfolio_assets and income_records tables."""
    op.drop_index('idx_income_user_type', table_name='income_records')
    op.drop_index('idx_income_user_period', table_name='income_records')
    op.drop_index('ix_income_records_user_id', table_name='income_records')
    op.drop_table('income_records')

    op.drop_index('idx_portfolio_user_type', table_name='portfolio_assets')
    op.drop_index('ix_portfolio_assets_user_id', table_name='portfolio_assets')
    op.drop_table('portfolio_assets')
