"""phase 5.1 #1.1 — media_objects: short-lived public URLs for private images

One additive table. Nothing existing is touched, so applying this on a
Telegram-only deployment is a no-op at runtime — no code reads the table
until a Zalo surface publishes its first chart.

``media_objects``
    Zalo fetches images by URL rather than accepting bytes, so a user's
    net worth chart has to be reachable without auth for a few minutes.
    The row stores ``sha256(token)`` and never the token, so a database
    leak yields no working URL. See backend/models/media_object.py for
    the reasoning behind each column and
    docs/current/phase-5.1/phase-5.1-detailed.md §Epic E1.

Revision ID: 20260803media51
Revises: 20260802zalo50
Create Date: 2026-08-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260803media51"
down_revision = "20260802zalo50"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "media_objects",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        # sha256 hex digest of the URL token — 64 chars, never the token.
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("storage_key", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        # Unique, not merely indexed: two rows sharing a digest would mean
        # one user's URL could resolve to another user's bytes. Postgres
        # backs both constraints with an index, which is also what the
        # resolver and the orphan sweep read.
        sa.UniqueConstraint("token_hash", name="uq_media_objects_token_hash"),
        sa.UniqueConstraint(
            "storage_key", name="uq_media_objects_storage_key"
        ),
    )

    op.create_index("ix_media_objects_user_id", "media_objects", ["user_id"])
    # The cleanup job's only query. Partial so swept history doesn't
    # bloat an index that is never read by age.
    op.create_index(
        "ix_media_objects_expiry_sweep",
        "media_objects",
        ["expires_at"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    # Only the two explicitly-created indexes are dropped here. The
    # unique constraints (and the indexes Postgres created to back them)
    # belong to the table and go with it.
    op.drop_index("ix_media_objects_expiry_sweep", table_name="media_objects")
    op.drop_index("ix_media_objects_user_id", table_name="media_objects")
    op.drop_table("media_objects")
