"""phase39 epic3 market data tables

Revision ID: p5j6k7l8m9n0
Revises: o4i5j6k7l8m9
Create Date: 2026-05-08 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "p5j6k7l8m9n0"
down_revision = "o4i5j6k7l8m9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "news_articles",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text()),
        sa.Column("url", sa.Text(), nullable=False, unique=True),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("related_symbols", postgresql.ARRAY(sa.String()), server_default="{}", nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("idx_news_published", "news_articles", ["published_at"])
    op.create_index("idx_news_symbols", "news_articles", ["related_symbols"], postgresql_using="gin")
    op.create_table(
        "bank_rates",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("bank_code", sa.String(length=20), nullable=False),
        sa.Column("bank_name", sa.String(length=100), nullable=False),
        sa.Column("tenor_months", sa.Integer(), nullable=False),
        sa.Column("rate_pct", sa.Numeric(5, 3), nullable=False),
        sa.Column("deposit_type", sa.String(length=20), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("snapshot_date", sa.Date(), server_default=sa.text("CURRENT_DATE"), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("bank_code", "tenor_months", "deposit_type", "snapshot_date", name="uq_bank_rate_snapshot"),
    )
    op.create_index("idx_bank_rates_lookup", "bank_rates", ["bank_code", "snapshot_date"])


def downgrade() -> None:
    op.drop_index("idx_bank_rates_lookup", table_name="bank_rates")
    op.drop_table("bank_rates")
    op.drop_index("idx_news_symbols", table_name="news_articles")
    op.drop_index("idx_news_published", table_name="news_articles")
    op.drop_table("news_articles")
