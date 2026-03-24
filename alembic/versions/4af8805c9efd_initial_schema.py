"""initial schema

Revision ID: 4af8805c9efd
Revises:
Create Date: 2026-03-24 04:56:13.488553

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '4af8805c9efd'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # users
    op.create_table(
        'users',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('telegram_id', sa.BigInteger(), nullable=False),
        sa.Column('telegram_handle', sa.String(255), nullable=True),
        sa.Column('display_name', sa.String(255), nullable=True),
        sa.Column('timezone', sa.String(50), nullable=False, server_default='Asia/Ho_Chi_Minh'),
        sa.Column('currency', sa.String(10), nullable=False, server_default='VND'),
        sa.Column('monthly_income', sa.Numeric(15, 2), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('telegram_id'),
    )

    # expenses
    op.create_table(
        'expenses',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('amount', sa.Numeric(15, 2), nullable=False),
        sa.Column('currency', sa.String(10), nullable=False, server_default='VND'),
        sa.Column('merchant', sa.String(500), nullable=True),
        sa.Column('category', sa.String(100), nullable=False),
        sa.Column('source', sa.String(50), nullable=False),
        sa.Column('expense_date', sa.Date(), nullable=False),
        sa.Column('month_key', sa.String(7), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('raw_data', postgresql.JSONB(), nullable=True),
        sa.Column('needs_review', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('gmail_message_id', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_expenses_user_id', 'expenses', ['user_id'])
    op.create_index('idx_expenses_month_key', 'expenses', ['user_id', 'month_key'])
    op.create_index('idx_expenses_category', 'expenses', ['user_id', 'category'])
    op.create_index(
        'idx_expenses_gmail_id', 'expenses', ['gmail_message_id'],
        postgresql_where=sa.text('gmail_message_id IS NOT NULL'),
    )

    # goals
    op.create_table(
        'goals',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('goal_name', sa.String(500), nullable=False),
        sa.Column('target_amount', sa.Numeric(15, 2), nullable=False),
        sa.Column('current_amount', sa.Numeric(15, 2), nullable=False, server_default='0'),
        sa.Column('deadline', sa.Date(), nullable=True),
        sa.Column('priority', sa.String(20), nullable=False, server_default='medium'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_goals_user_id', 'goals', ['user_id'])

    # monthly_reports
    op.create_table(
        'monthly_reports',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('month_key', sa.String(7), nullable=False),
        sa.Column('total_expense', sa.Numeric(15, 2), nullable=False),
        sa.Column('total_income', sa.Numeric(15, 2), nullable=True),
        sa.Column('savings_amount', sa.Numeric(15, 2), nullable=True),
        sa.Column('savings_rate', sa.Numeric(5, 2), nullable=True),
        sa.Column('breakdown_by_category', postgresql.JSONB(), nullable=False),
        sa.Column('vs_previous_month', postgresql.JSONB(), nullable=True),
        sa.Column('goal_progress', postgresql.JSONB(), nullable=True),
        sa.Column('report_text', sa.Text(), nullable=True),
        sa.Column('generated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'month_key', name='uq_report_user_month'),
    )
    op.create_index('idx_reports_user_month', 'monthly_reports', ['user_id', 'month_key'])

    # market_snapshots
    op.create_table(
        'market_snapshots',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('snapshot_date', sa.Date(), nullable=False),
        sa.Column('asset_code', sa.String(50), nullable=False),
        sa.Column('asset_type', sa.String(50), nullable=False),
        sa.Column('asset_name', sa.String(500), nullable=True),
        sa.Column('price', sa.Numeric(15, 4), nullable=True),
        sa.Column('change_1d_pct', sa.Numeric(8, 4), nullable=True),
        sa.Column('change_1w_pct', sa.Numeric(8, 4), nullable=True),
        sa.Column('change_1m_pct', sa.Numeric(8, 4), nullable=True),
        sa.Column('extra_data', postgresql.JSONB(), nullable=True),
        sa.Column('source_url', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('snapshot_date', 'asset_code', name='uq_snapshot_date_asset'),
    )
    op.create_index('idx_market_date', 'market_snapshots', ['snapshot_date'], postgresql_ops={'snapshot_date': 'DESC'})
    op.create_index('idx_market_asset', 'market_snapshots', ['asset_code', 'snapshot_date'], postgresql_ops={'snapshot_date': 'DESC'})

    # investment_logs
    op.create_table(
        'investment_logs',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('log_date', sa.Date(), nullable=False),
        sa.Column('market_context', postgresql.JSONB(), nullable=False),
        sa.Column('user_financial_context', postgresql.JSONB(), nullable=False),
        sa.Column('recommendation', sa.Text(), nullable=False),
        sa.Column('action_taken', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_investment_logs_user', 'investment_logs', ['user_id', 'log_date'])

    # llm_cache
    op.create_table(
        'llm_cache',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('cache_key', sa.String(500), nullable=False),
        sa.Column('model', sa.String(100), nullable=False),
        sa.Column('prompt_hash', sa.String(64), nullable=False),
        sa.Column('response', sa.Text(), nullable=False),
        sa.Column('tokens_used', sa.Integer(), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('cache_key'),
    )
    op.create_index('idx_llm_cache_key', 'llm_cache', ['cache_key'])
    op.create_index('idx_llm_cache_expires', 'llm_cache', ['expires_at'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('llm_cache')
    op.drop_table('investment_logs')
    op.drop_table('market_snapshots')
    op.drop_table('monthly_reports')
    op.drop_table('goals')
    op.drop_table('expenses')
    op.drop_table('users')
