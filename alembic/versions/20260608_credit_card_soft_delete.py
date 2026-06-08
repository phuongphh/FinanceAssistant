"""soft-delete column for credit_cards

Adds ``credit_cards.deleted_at`` so the bot can hide a card from the
spending menu and the NLU source-matcher without losing the row — the
existing ``expenses.source_credit_card_id`` FK rows (history,
debt-balance ledger) must keep resolving even after the user removes
the card.

The unique ``(user_id, bank_name)`` constraint is converted to a
partial unique index that only applies to live rows, so a user can
re-add the same bank after deleting it.

Revision ID: 20260608ccsoftdel
Revises: 20260605relaxwalletck
Create Date: 2026-06-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260608ccsoftdel"
down_revision = "20260605relaxwalletck"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "credit_cards",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.drop_constraint(
        "uq_credit_cards_user_bank_name", "credit_cards", type_="unique"
    )
    op.create_index(
        "uq_credit_cards_user_bank_name_active",
        "credit_cards",
        ["user_id", "bank_name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "idx_credit_cards_user_active",
        "credit_cards",
        ["user_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_credit_cards_user_active", table_name="credit_cards")
    op.drop_index(
        "uq_credit_cards_user_bank_name_active", table_name="credit_cards"
    )
    op.create_unique_constraint(
        "uq_credit_cards_user_bank_name",
        "credit_cards",
        ["user_id", "bank_name"],
    )
    op.drop_column("credit_cards", "deleted_at")
