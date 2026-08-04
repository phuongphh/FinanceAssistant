"""phase 5.1 #4.2 — users.telegram_id nullable so Zalo can be a signup channel

Until 5.1 every account started on Telegram, so ``telegram_id`` being
``NOT NULL`` cost nothing. #4.3 lets a user sign up from the Zalo OA and
never touch Telegram; that user has no Telegram id to store, and there is
no honest placeholder for one — a sentinel would collide on the unique
index as soon as a second Zalo-only user arrived, and every
``send_message(chat_id=...)`` built from it would address a chat that
does not exist. So the column becomes nullable.

The unique index is deliberately left exactly as it is. Postgres treats
NULLs as distinct inside a unique index, so any number of Zalo-only rows
coexist while two real Telegram ids still cannot — a partial index
(``WHERE telegram_id IS NOT NULL``) would buy nothing and would have to
be dropped and rebuilt on a live table.

Downgrade only succeeds while no Zalo-only user exists. That is on
purpose: silently inventing ids or deleting accounts to make a rollback
tidy would lose real users. The check runs first and raises with a count
so the operator can decide.

Revision ID: 20260803tgnullable
Revises: 20260803media51
Create Date: 2026-08-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260803tgnullable"
down_revision = "20260803media51"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "telegram_id",
        existing_type=sa.BigInteger(),
        nullable=True,
    )


def downgrade() -> None:
    orphans = (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM users WHERE telegram_id IS NULL"))
        .scalar()
        or 0
    )
    if orphans:
        raise RuntimeError(
            f"{orphans} user(s) have no telegram_id (Zalo-only accounts). "
            "Restoring NOT NULL would require inventing or deleting their "
            "identity — resolve those rows by hand first, then re-run."
        )
    op.alter_column(
        "users",
        "telegram_id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )
