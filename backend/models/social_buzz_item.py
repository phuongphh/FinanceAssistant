"""Hóng hớt — hot social/tech/economy items an admin enters by hand (#1061).

Phase 1 of the daily "Hóng hớt" digest has no crawler: the operator
(Nuitruc) reads Threads/TikTok and the tech/economy press, then types the
items into the admin portal. This table is that hand-curated feed.

Deliberately separate from ``news_articles``: that table is the RSS
market-news pipeline (fixed sources, ``url`` unique, no category, no
image). Social items often have no public link at all, two items may
point at the same viral post, and they carry an illustration.

Not user-scoped content — one feed shared by every user, owned by the
admin who wrote it (``created_by``). Like ``admin_users`` /
``admin_audit_log`` it therefore has no ``user_id`` column.

Soft delete: ``is_active=false`` hides an item from the digest but keeps
it editable in the portal; ``deleted_at`` is "xoá" — gone from the portal
too, but the row survives per the project's no-hard-delete rule.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base

SOURCE_THREAD = "thread"
SOURCE_TIKTOK = "tiktok"
SOURCE_MANUAL = "manual"
SOURCE_TYPES = (SOURCE_THREAD, SOURCE_TIKTOK, SOURCE_MANUAL)

CATEGORY_SOCIAL = "social"
CATEGORY_TECH = "tech"
CATEGORY_ECONOMY = "economy"
CATEGORIES = (CATEGORY_SOCIAL, CATEGORY_TECH, CATEGORY_ECONOMY)


def _in_check(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


class SocialBuzzItem(Base):
    __tablename__ = "social_buzz_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    # Optional and NOT unique — a TikTok trend may have no stable public
    # link, and two items can legitimately cite the same post.
    url: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    # String + CHECK rather than a Postgres ENUM: adding a source later
    # (facebook, youtube…) is then a constraint swap, not ALTER TYPE.
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    # SET NULL so deactivating/removing an operator account never takes
    # the content they wrote with it.
    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("admin_users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            _in_check("source_type", SOURCE_TYPES),
            name="ck_social_buzz_items_source_type",
        ),
        CheckConstraint(
            _in_check("category", CATEGORIES),
            name="ck_social_buzz_items_category",
        ),
        # Serves "5 newest active items in a category" for the digest.
        Index(
            "ix_social_buzz_items_category_active_created",
            "category",
            "is_active",
            "created_at",
        ),
    )
