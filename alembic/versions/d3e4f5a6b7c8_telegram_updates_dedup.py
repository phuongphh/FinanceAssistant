"""phase A1 — telegram_updates dedup table

Revision ID: d3e4f5a6b7c8
Revises: c1d2e3f4a5b6
Create Date: 2026-04-23 00:00:00.000000

Creates the ``telegram_updates`` table used to:
- Dedup retried Telegram webhook deliveries (PK = update_id).
- Track background-processing status for orphan recovery on restart.

Rationale in docs/strategy/scaling-refactor-A.md §A1.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd3e4f5a6b7c8'
down_revision: Union[str, Sequence[str], None] = 'c1d2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'telegram_updates',
        sa.Column('update_id', sa.BigInteger(), nullable=False),
        # Nullable because the webhook arrives before the user is resolved
        # (including /start for users that don't yet exist). Populated by
        # the worker once the user is known — enables per-user replay /
        # audit / deletion. See CLAUDE.md §0 multi-tenant rule.
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column(
            'received_at', sa.DateTime(timezone=True),
            server_default=sa.text('NOW()'), nullable=False,
        ),
        sa.Column(
            'status', sa.String(20),
            server_default=sa.text("'processing'"), nullable=False,
        ),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('payload', postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('update_id'),
    )
    # Partial index — only scans rows still in flight for orphan recovery.
    op.create_index(
        'idx_telegram_updates_processing',
        'telegram_updates',
        ['received_at'],
        postgresql_where=sa.text("status = 'processing'"),
    )
    op.create_index(
        'idx_telegram_updates_received_at',
        'telegram_updates',
        ['received_at'],
    )
    op.create_index(
        'idx_telegram_updates_user_id',
        'telegram_updates',
        ['user_id'],
    )


def downgrade() -> None:
    op.drop_index('idx_telegram_updates_user_id', table_name='telegram_updates')
    op.drop_index('idx_telegram_updates_received_at', table_name='telegram_updates')
    op.drop_index('idx_telegram_updates_processing', table_name='telegram_updates')
    op.drop_table('telegram_updates')
