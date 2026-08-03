"""Zalo OA OAuth credentials (Phase 5.0 #1.3).

Zalo's ``access_token`` lives one hour, so the token cannot live in an
env var — it has to be refreshed by the running process and shared
across workers. That makes it row data, and this is the row.

**Multi-tenancy exception (documented on purpose).** CLAUDE.md requires
every table to carry ``user_id``. This one does not: a Zalo Official
Account credential belongs to the OA, not to any user, and all of our
users are served by the same OA. Adding a ``user_id`` here would be a
lie about ownership. The PK is ``app_id`` so a future multi-OA setup
(one OA per tenant) is a straight insert, not a migration.

The ``refresh_pending_*`` columns implement the write-ahead half of the
refresh protocol — see ``docs/conventions/zalo-operations.md``
§Token refresh protocol for why a plain transaction is not enough.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class ZaloOACredential(Base):
    __tablename__ = "zalo_oa_credentials"

    app_id: Mapped[str] = mapped_column(String(64), primary_key=True)

    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    # When the current access_token stops working. NULL means "unknown",
    # which the service treats as expired — better one wasted refresh
    # than an hour of 401s.
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Set (and COMMITTED) immediately before the refresh HTTP call, cleared
    # after it succeeds. A non-NULL value on startup means the process died
    # mid-refresh and we cannot know whether Zalo consumed the token — the
    # service refuses to guess. See the runbook.
    refresh_pending_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_pending_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Observability: how many refreshes this credential has been through,
    # and when it last succeeded. A refresh counter climbing faster than
    # once an hour means something is stampeding the lock.
    refresh_count: Mapped[int] = mapped_column(default=0, nullable=False)
    last_refreshed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
