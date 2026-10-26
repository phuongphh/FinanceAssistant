"""Hóng hớt #1061 — social_buzz_items table for admin-entered hot items.

Phase 1 of the "Hóng hớt" daily digest is curated by hand in the admin
portal (Threads/TikTok/tech/economy). See
:mod:`backend.models.social_buzz_item` for why this is a new table rather
than more columns on ``news_articles``.

Revision ID: 20261026socialbuzz
Revises: 20260813zaloinflight
Create Date: 2026-10-26
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261026socialbuzz"
down_revision = "20260813zaloinflight"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "social_buzz_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("admin_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "source_type IN ('thread', 'tiktok', 'manual')",
            name="ck_social_buzz_items_source_type",
        ),
        sa.CheckConstraint(
            "category IN ('social', 'tech', 'economy')",
            name="ck_social_buzz_items_category",
        ),
    )
    op.create_index(
        "ix_social_buzz_items_category_active_created",
        "social_buzz_items",
        ["category", "is_active", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_social_buzz_items_category_active_created",
        table_name="social_buzz_items",
    )
    op.drop_table("social_buzz_items")
