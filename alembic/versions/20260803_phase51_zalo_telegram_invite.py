"""phase 5.1 #4.3 — one-time "come to Telegram too" invite markers on users

Zalo is reactive-first (chốt 02/08/2026): the OA only speaks when the user
just spoke, inside the 48h window. A user who signed up on Zalo and never
touched Telegram therefore gets no briefing, no empathy nudge, no alert
while they are quiet — the very things that make Bé Tiền a companion
rather than a ledger. So at the end of Zalo onboarding we invite them to
Telegram once, honestly, and never bring it up again.

Two columns rather than one, because they answer different questions and
only one of them gates the send:

``zalo_telegram_invite_at``       NULL → never invited. This alone is the
                                  "at most once" gate, so an invitation
                                  the user simply ignored is never
                                  repeated either — silence is an answer.
``zalo_telegram_invite_response`` what they chose ("declined"), or NULL
                                  while unanswered. "Declined" and
                                  "ignored" mean different things to
                                  anyone reading this row later.

Accepting leaves no mark here: the accept path is a URL button that opens
Telegram, so acceptance shows up as a Telegram id, not as a message
coming back to Zalo.

Both columns are nullable with no server default — NULL is the correct
state for every existing row (nobody has been invited yet) and for every
Telegram-first user (nobody ever will be).

Revision ID: 20260803zaloinvite
Revises: 20260803tgnullable
Create Date: 2026-08-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260803zaloinvite"
down_revision = "20260803tgnullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("zalo_telegram_invite_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("zalo_telegram_invite_response", sa.String(20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "zalo_telegram_invite_response")
    op.drop_column("users", "zalo_telegram_invite_at")
