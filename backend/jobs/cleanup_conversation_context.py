"""Hourly prune of the short-term conversation buffer.

``conversation_context`` is append-only: every user message and every
bot reply writes a row, and nothing ever deletes one.
:mod:`backend.services.conversation_context_service` enforces its TTL on
*read* — the query filters ``created_at >= now - DEFAULT_TTL_MINUTES``
and caps the row count with ``LIMIT``. That is the right shape for the
read path (a row that ages out mid-session must disappear immediately,
not whenever a sweep happens to run) but it means the table itself only
ever grows. A row fifteen minutes old is already invisible to every
reader in the system; it is pure storage, plus dead weight in
``idx_conv_ctx_user_time``, which is the index the agent hits before
every LLM call.

Hard delete, not soft delete
----------------------------
The project rule is to soft-delete user data. This table is the
exception, deliberately: it is a prompt-assembly buffer, not a record of
anything. Its rows are a truncated copy (280 chars) of content that is
already stored properly — user messages in ``events``, bot replies in
the transcript the adapters log — and nothing reads it after the TTL
expires, so there is no "restore" that a ``deleted_at`` column would
enable. A soft delete here would keep growing the same index for no
recoverable value, and would keep raw user text on disk indefinitely,
which the model's own PII note argues against.

Retention window
----------------
``RETENTION_DAYS`` is days, against a read TTL measured in minutes. The
gap is deliberate slack, not indecision: it leaves a window where a
production incident can still be reconstructed from what the agent
actually saw, and it means a scheduler outage of a day or two changes
nothing. Shrinking it towards the TTL buys almost no disk (the buffer is
tiny per user) and gives up the only debugging value the table has after
it stops being read.

Batching
--------
``BATCH_LIMIT`` rows per run, same reasoning as the media sweep: a first
run against a table that has never been pruned could otherwise hold one
transaction open over millions of rows. The next hourly run picks up the
remainder, so a backlog drains over hours instead of blocking writes.

Idempotency
-----------
Running twice back to back is a no-op the second time — the cutoff
filter excludes everything the first pass deleted.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from backend.database import get_session_factory
from backend.models.conversation_context import ConversationContext

logger = logging.getLogger(__name__)

# Rows removed per run. See the module docstring on batching.
BATCH_LIMIT = 5000

# How long a row survives after it stops being readable. See the module
# docstring — this is a debugging window, not a functional TTL.
RETENTION_DAYS = 7


@dataclass
class ConversationContextCleanupResult:
    """What one sweep removed.

    ``deleted_rows`` at ``BATCH_LIMIT`` means the sweep was capped and
    more rows are still pending — worth noticing if it repeats, since a
    steady stream of full batches means the hourly cadence is no longer
    keeping up with write volume.
    """

    deleted_rows: int = 0
    batch_capped: bool = False


async def _prune(db, cutoff: datetime) -> int:
    """Delete up to ``BATCH_LIMIT`` rows older than ``cutoff``."""
    # Select the ids first, then delete by id. Postgres has no LIMIT on
    # DELETE, and a subquery is the standard way to bound one — doing it
    # in two statements keeps the intent readable and lets the id list
    # ride the primary key on the way out.
    ids = (
        (
            await db.execute(
                select(ConversationContext.id)
                .where(ConversationContext.created_at < cutoff)
                .order_by(ConversationContext.created_at)
                .limit(BATCH_LIMIT)
            )
        )
        .scalars()
        .all()
    )
    if not ids:
        return 0

    await db.execute(
        delete(ConversationContext).where(ConversationContext.id.in_(ids))
    )
    # This job owns its own session, so committing here is the job acting
    # as its own transaction boundary — not a service reaching past its
    # layer.
    await db.commit()
    return len(ids)


async def cleanup_conversation_context() -> ConversationContextCleanupResult:
    """Entry point registered with the scheduler. Never raises."""
    result = ConversationContextCleanupResult()
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)

    try:
        # Inside the try on purpose: resolving the engine can fail too
        # (bad DSN, pool exhausted at startup), and the docstring above
        # promises the scheduler never sees an exception from here.
        session_factory = get_session_factory()
        async with session_factory() as db:
            result.deleted_rows = await _prune(db, cutoff)
    except Exception:
        # A failed prune is not an incident: the rows are already
        # invisible to readers, and the next hour retries. Swallowing
        # keeps one bad run from killing the scheduler thread.
        logger.exception("conversation-context-cleanup: prune failed")
        return result

    result.batch_capped = result.deleted_rows >= BATCH_LIMIT
    logger.info(
        "conversation-context-cleanup: deleted_rows=%d cutoff=%s",
        result.deleted_rows,
        cutoff.isoformat(),
    )
    if result.batch_capped:
        logger.warning(
            "conversation-context-cleanup: hit the %d-row batch cap — a "
            "backlog is draining, or write volume has outgrown the hourly "
            "cadence",
            BATCH_LIMIT,
        )
    return result
