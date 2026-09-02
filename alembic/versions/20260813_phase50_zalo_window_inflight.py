"""Phase 5.0 #1029(4) — track in-flight Zalo sends across window rotation.

``record_inbound`` used to zero ``free_msg_count`` on every new inbound
message. A send that had already reserved a slot but whose OA request had
not returned was erased by that reset, then still counted by Zalo against
the *new* window — the local row believed all 8 were free, so the OA could
push 9+ consulting messages into one window.

``inflight_count`` is what makes the reset able to tell the difference:
reservations still in flight are carried into the new window, everything
else is released as before.

Revision ID: 20260813zaloinflight
Revises: 20260813tokenpurpose
Create Date: 2026-08-13
"""

import sqlalchemy as sa
from alembic import op

revision = "20260813zaloinflight"
down_revision = "20260813tokenpurpose"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "zalo_message_window",
        sa.Column(
            "inflight_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Reserved sends not yet settled by the OA response.",
        ),
    )


def downgrade() -> None:
    op.drop_column("zalo_message_window", "inflight_count")
