"""phase 5.0 zalo channel — credentials, inbound dedup, 48h window

Three additive tables behind the ``ZALO_CHANNEL_ENABLED`` flag. Nothing
existing is touched, so applying this on a Telegram-only deployment is a
no-op at runtime.

``zalo_oa_credentials``
    Holds the OAuth pair. Zalo's access_token lives one hour, so it cannot
    live in an env var. ``refresh_pending_*`` is the write-ahead marker for
    the crash-safe refresh protocol — see
    docs/conventions/zalo-operations.md §Token refresh protocol.
    Deliberately has no ``user_id``: an OA credential belongs to the OA.

``zalo_updates``
    Inbound dedup queue mirroring ``telegram_updates``. Zalo re-delivers on
    any non-2xx, so without this a slow handler double-records a capture.

``zalo_message_window``
    Local accounting for Zalo's 48h reply window and 8-free-message quota,
    so we stop before burning a platform rejection.

Revision ID: 20260802zalo50
Revises: 20260712dqcohort46
Create Date: 2026-08-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260802zalo50"
down_revision = "20260712dqcohort46"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "zalo_oa_credentials",
        sa.Column("app_id", sa.String(length=64), primary_key=True),
        sa.Column("access_token", sa.Text(), nullable=True),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refresh_pending_token", sa.Text(), nullable=True),
        sa.Column("refresh_pending_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "refresh_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "zalo_updates",
        sa.Column("msg_id", sa.String(length=128), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("zalo_user_id", sa.String(length=64), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="processing",
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
    )
    op.create_index("idx_zalo_updates_user_id", "zalo_updates", ["user_id"])
    op.create_index(
        "idx_zalo_updates_zalo_user_id", "zalo_updates", ["zalo_user_id"]
    )
    op.create_index(
        "idx_zalo_updates_received_at", "zalo_updates", ["received_at"]
    )
    # Partial index: the orphan-recovery scan only ever looks at in-flight
    # rows, so keep the index proportional to concurrency, not to history.
    op.create_index(
        "idx_zalo_updates_processing",
        "zalo_updates",
        ["received_at"],
        postgresql_where=sa.text("status = 'processing'"),
    )

    op.create_table(
        "zalo_message_window",
        sa.Column("zalo_user_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("last_inbound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "window_expires_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "free_msg_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "idx_zalo_message_window_user_id", "zalo_message_window", ["user_id"]
    )
    op.create_index(
        "idx_zalo_message_window_expires",
        "zalo_message_window",
        ["window_expires_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_zalo_message_window_expires", table_name="zalo_message_window")
    op.drop_index("idx_zalo_message_window_user_id", table_name="zalo_message_window")
    op.drop_table("zalo_message_window")

    op.drop_index("idx_zalo_updates_processing", table_name="zalo_updates")
    op.drop_index("idx_zalo_updates_received_at", table_name="zalo_updates")
    op.drop_index("idx_zalo_updates_zalo_user_id", table_name="zalo_updates")
    op.drop_index("idx_zalo_updates_user_id", table_name="zalo_updates")
    op.drop_table("zalo_updates")

    op.drop_table("zalo_oa_credentials")
