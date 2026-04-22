"""phase 2 — onboarding columns, user_milestones, user_streaks

Revision ID: c1d2e3f4a5b6
Revises: b2c3d4e5f6a7
Create Date: 2026-04-22 09:00:00.000000

Phase 2 foundation (Issue #37):
- Add onboarding fields to `users` (display_name already exists — skipped).
- Create `user_milestones` table for Memory Moments feature.
- Create `user_streaks` table for daily-activity streak tracking.

`user_events` is intentionally NOT created — Phase 1's generic `events`
table already has the exact shape needed (user_id UUID, event_type,
properties JSONB, timestamp) and is the shared log for analytics and
empathy-cooldown queries.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- users: onboarding fields -------------------------------------
    # display_name already exists on users (String(255)) — reused as-is.
    op.add_column(
        'users',
        sa.Column('primary_goal', sa.String(30), nullable=True),
    )
    op.add_column(
        'users',
        sa.Column(
            'onboarding_step',
            sa.Integer(),
            server_default=sa.text('0'),
            nullable=False,
        ),
    )
    op.add_column(
        'users',
        sa.Column(
            'onboarding_completed_at',
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        'users',
        sa.Column(
            'onboarding_skipped',
            sa.Boolean(),
            server_default=sa.text('false'),
            nullable=False,
        ),
    )
    op.create_index(
        'idx_users_onboarding_step', 'users', ['onboarding_step']
    )

    # --- user_milestones ---------------------------------------------
    op.create_table(
        'user_milestones',
        sa.Column(
            'id', sa.UUID(), nullable=False,
            server_default=sa.text('gen_random_uuid()'),
        ),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('milestone_type', sa.String(50), nullable=False),
        sa.Column(
            'achieved_at', sa.DateTime(timezone=True),
            server_default=sa.text('NOW()'), nullable=False,
        ),
        sa.Column('celebrated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('extra', postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'user_id', 'milestone_type',
            name='uq_user_milestone_type',
        ),
    )
    op.create_index(
        'idx_milestones_user_type', 'user_milestones',
        ['user_id', 'milestone_type'],
    )
    op.create_index(
        'idx_milestones_celebrated_at', 'user_milestones', ['celebrated_at'],
    )

    # --- user_streaks -------------------------------------------------
    op.create_table(
        'user_streaks',
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column(
            'current_streak', sa.Integer(),
            server_default=sa.text('0'), nullable=False,
        ),
        sa.Column(
            'longest_streak', sa.Integer(),
            server_default=sa.text('0'), nullable=False,
        ),
        sa.Column('last_active_date', sa.Date(), nullable=True),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True),
            server_default=sa.text('NOW()'), nullable=False,
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('user_id'),
    )


def downgrade() -> None:
    op.drop_table('user_streaks')

    op.drop_index('idx_milestones_celebrated_at', table_name='user_milestones')
    op.drop_index('idx_milestones_user_type', table_name='user_milestones')
    op.drop_table('user_milestones')

    op.drop_index('idx_users_onboarding_step', table_name='users')
    op.drop_column('users', 'onboarding_skipped')
    op.drop_column('users', 'onboarding_completed_at')
    op.drop_column('users', 'onboarding_step')
    op.drop_column('users', 'primary_goal')
