"""Phase 5.1 #1.1 — short-lived public URLs for user-private images.

Telegram takes image *bytes* on the wire. Zalo takes a *URL* and fetches
it itself, which means every chart we want to show a Zalo user has to sit
on a public, unauthenticated endpoint for a while. The bytes in question
are that user's net worth curve — so the design assumption here is that
the URL *is* the credential, and everything else follows from limiting
what that credential can do.

Three properties carry the privacy claim:

``token_hash``
    We store ``sha256(token)``, never the token. Reading this table gives
    an attacker byte sizes and timestamps but no way to construct a
    working URL — the same reason a password table stores digests. The
    token itself exists only in the URL we hand to Zalo and in the
    requests that come back.

``expires_at``
    Default TTL is 15 minutes (the caller passes it; see
    :mod:`backend.services.media_url_service`). A leaked URL is worth
    something for minutes, not forever.

``deleted_at``
    Soft delete per the project convention, and it doubles as the
    revocation switch: the cleanup job stamps it, the resolver treats a
    stamped row as absent, and the row survives so we can still tell
    "expired" apart from "never existed" in our own logs — a distinction
    the HTTP surface deliberately refuses to make.

``storage_key`` points at the bytes. It is a bare uuid4 hex, generated
independently of the token, so guessing a filename on disk still doesn't
tell you which user it belongs to without the DB, and having the DB
doesn't give you the URL.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base

# sha256 hex digest length. Pinned as a constant because the migration,
# the model and the service all have to agree on it.
TOKEN_HASH_LENGTH = 64


class MediaObject(Base):
    __tablename__ = "media_objects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Multi-tenancy from day 1 — every row belongs to exactly one user,
    # which is what makes "delete everything for this user" answerable
    # and what lets the cleanup job report per-user volume if we ever
    # need it. NOT NULL: an image with no owner has no business existing
    # on a public URL.
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )

    # sha256 of the URL token. Unique because a collision here would let
    # one user's URL resolve to another user's bytes. Postgres backs a
    # UNIQUE constraint with an index, so the resolver's lookup is served
    # by the same object that enforces the invariant.
    token_hash: Mapped[str] = mapped_column(
        String(TOKEN_HASH_LENGTH), nullable=False, unique=True
    )

    # Served verbatim as the response Content-Type. Whatever produced the
    # bytes decides this; the resolver never sniffs.
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)

    # BigInteger rather than Integer: charts are ~200KB today, but a
    # column that can't hold a large PDF is a migration waiting to happen.
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Opaque handle the storage backend understands. Unique so the
    # orphan sweep can go file → row in one lookup.
    storage_key: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("now()"),
    )
    # NULL = live. Set by the cleanup job, or by hand to revoke a URL
    # early. Never hard-deleted.
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        # The cleanup job's only query: live rows past their expiry.
        # Partial on ``deleted_at IS NULL`` so already-swept rows don't
        # bloat it — the table is append-heavy and never read by age.
        Index(
            "ix_media_objects_expiry_sweep",
            "expires_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover — debugging aid
        # Deliberately omits token_hash. Even the digest has no reason to
        # appear in a log line or a traceback.
        return (
            f"<MediaObject id={self.id} user_id={self.user_id} "
            f"bytes={self.byte_size} expires_at={self.expires_at}>"
        )
