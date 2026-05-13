"""phase4b epic4 — zalo adapter foundation

Revision ID: 20261101p4bzalo
Revises: 20261001p4bcashflow
Create Date: 2026-11-01 00:00:00.000000

Phase 4B Epic 4 (Stories P4B-S21..S24):

1. Adds ``users.zalo_user_id`` — populated when a user redeems a
   linking token via the Zalo webhook. NULL means "Telegram-only".
2. Creates ``zalo_link_tokens`` — short-lived (10-min TTL) single-use
   codes that let the Zalo webhook bind an incoming Zalo user_id back
   to our internal user row.

The split (users column vs token table) keeps the hot-path notifier
resolver (``get_notifiers_for_user``) a single column read; tokens are
ephemeral and only consulted during the linking flow.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261101p4bzalo"
down_revision = "20261001p4bcashflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("zalo_user_id", sa.String(64), nullable=True),
    )
    # Partial unique constraint so two users can't claim the same Zalo
    # account, while still allowing the column to stay NULL for the
    # majority of users who never link.
    op.create_index(
        "idx_users_zalo_user_id",
        "users",
        ["zalo_user_id"],
        unique=True,
        postgresql_where=sa.text("zalo_user_id IS NOT NULL"),
    )

    op.create_table(
        "zalo_link_tokens",
        sa.Column("token", sa.String(16), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_zalo_link_tokens_user_id",
        "zalo_link_tokens",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_zalo_link_tokens_user_id", table_name="zalo_link_tokens")
    op.drop_table("zalo_link_tokens")
    op.drop_index("idx_users_zalo_user_id", table_name="users")
    op.drop_column("users", "zalo_user_id")
