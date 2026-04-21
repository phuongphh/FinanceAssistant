"""add events table for analytics tracking

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-20 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create events table for analytics tracking."""
    op.create_table(
        'events',
        sa.Column(
            'id', sa.UUID(), nullable=False,
            server_default=sa.text('gen_random_uuid()'),
        ),
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column('event_type', sa.String(100), nullable=False),
        sa.Column('properties', postgresql.JSONB(), nullable=True),
        sa.Column(
            'timestamp', sa.DateTime(timezone=True),
            server_default=sa.text('NOW()'), nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_events_user_id', 'events', ['user_id'])
    op.create_index('ix_events_event_type', 'events', ['event_type'])
    op.create_index('ix_events_timestamp', 'events', ['timestamp'])
    op.create_index('idx_events_user_type', 'events', ['user_id', 'event_type'])
    op.create_index(
        'idx_events_type_timestamp', 'events', ['event_type', 'timestamp']
    )


def downgrade() -> None:
    """Drop events table."""
    op.drop_index('idx_events_type_timestamp', table_name='events')
    op.drop_index('idx_events_user_type', table_name='events')
    op.drop_index('ix_events_timestamp', table_name='events')
    op.drop_index('ix_events_event_type', table_name='events')
    op.drop_index('ix_events_user_id', table_name='events')
    op.drop_table('events')
