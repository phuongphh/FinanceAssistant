"""phase 5.0 #1028 — give zalo_link_tokens a purpose discriminator

``zalo_link_tokens`` used to serve exactly one flow: a human types
``BT-XXXXXX`` from Telegram into the Zalo OA. #1028 adds a second,
opposite flow — a Zalo-first user taps an invite and lands in Telegram
carrying a token in the ``/start`` deep link — and the two must never be
mistaken for each other:

* ``issue_link_token`` re-uses any active token belonging to the user, so
  without a discriminator ``/link_zalo`` would hand back an adoption
  token and display 16 random URL-safe characters as a code to type.
* ``redeem_link_token`` binds ``users.zalo_user_id``; an adoption token
  pasted into Zalo must be rejected rather than silently re-bound.

``NOT NULL DEFAULT 'zalo_link'`` because every existing row is, by
construction, a pairing token — the adoption flow does not exist yet on
any deployed environment (``ZALO_CHANNEL_ENABLED`` is off).

Revision ID: 20260813tokenpurpose
Revises: 20260803zaloinvite
Create Date: 2026-08-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260813tokenpurpose"
down_revision = "20260803zaloinvite"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "zalo_link_tokens",
        sa.Column(
            "purpose",
            sa.String(20),
            nullable=False,
            server_default="zalo_link",
        ),
    )


def downgrade() -> None:
    op.drop_column("zalo_link_tokens", "purpose")
