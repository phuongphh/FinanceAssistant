"""phase39 epic4 analytics and alerts

Revision ID: q6k7l8m9n0p1
Revises: p5j6k7l8m9n0
Create Date: 2026-05-08 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "q6k7l8m9n0p1"
down_revision = "p5j6k7l8m9n0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stock_historical_prices",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("price_date", sa.Date(), nullable=False),
        sa.Column("close_price", sa.Numeric(20, 4), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("symbol", "price_date", name="uq_stock_historical_symbol_date"),
    )
    op.create_index("idx_stock_historical_lookup", "stock_historical_prices", ["symbol", "price_date"])

    op.create_table(
        "notification_settings",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("price_alerts_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_table(
        "price_alerts_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("change_pct", sa.Numeric(8, 3), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("idx_price_alerts_user_day", "price_alerts_log", ["user_id", "sent_at"])
    op.create_index("idx_price_alerts_symbol_cooldown", "price_alerts_log", ["user_id", "symbol", "sent_at"])


def downgrade() -> None:
    op.drop_index("idx_price_alerts_symbol_cooldown", table_name="price_alerts_log")
    op.drop_index("idx_price_alerts_user_day", table_name="price_alerts_log")
    op.drop_table("price_alerts_log")
    op.drop_table("notification_settings")
    op.drop_index("idx_stock_historical_lookup", table_name="stock_historical_prices")
    op.drop_table("stock_historical_prices")
