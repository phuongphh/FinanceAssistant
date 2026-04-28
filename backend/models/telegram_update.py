"""Telegram update dedup + background-processing queue.

Every incoming Telegram webhook update is recorded here **before** being
dispatched. Serves two purposes:

1. Dedup — Telegram retries on network blips. The PK is the raw
   ``update_id`` (monotonic per bot) so ``INSERT ... ON CONFLICT
   (update_id) DO NOTHING`` is an atomic dedup primitive.
2. Orphan recovery — if the process crashes between claiming an update
   and finishing work, the row stays at ``status='processing'``. A
   startup hook re-enqueues rows older than a cutoff.

See docs/archive/scaling-refactor-A.md §A1 for the full rationale.
"""
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


# Status values — kept as string constants (not enum) to avoid needing a
# migration every time a new state is introduced.
STATUS_PROCESSING = "processing"
STATUS_DONE = "done"
STATUS_FAILED = "failed"


class TelegramUpdate(Base):
    __tablename__ = "telegram_updates"

    update_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # Nullable — the webhook runs before the user is resolved (and /start
    # fires for users that don't yet exist in our DB). Populated by the
    # background worker after it resolves the Telegram user. Matches the
    # `events` table convention. Enables per-user replay / audit /
    # GDPR-style deletion — satisfies the multi-tenant guarantee in
    # CLAUDE.md §0.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default=STATUS_PROCESSING, nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        # Partial index — only rows still in flight matter for the
        # orphan-recovery scan. Keeps the index tiny regardless of
        # historical volume.
        Index(
            "idx_telegram_updates_processing",
            "received_at",
            postgresql_where=text("status = 'processing'"),
        ),
        Index("idx_telegram_updates_received_at", "received_at"),
    )
