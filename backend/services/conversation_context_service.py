"""Short-term conversation context — read/write helpers.

The agent layer calls these around every free-form text turn:

  ``save_message`` after we know what the user said and what we
  replied, ``get_recent_messages`` right before the next LLM call
  so the prompt sees the last few turns.

Design decisions:

- **TTL on read, not write.** Rows are append-only; the read query
  filters by ``created_at >= now - TTL``. Stale rows linger in the
  table until a separate cleanup job (or manual prune) catches up.
  Cheaper than scheduling a delete for every write, and the index
  lets the filter scan only recent rows for the user.

- **Buffer size enforced on read.** We always insert; we just LIMIT
  the read to the last N rows. That keeps the write path one
  statement (no transactional read-modify-write) and the buffer is
  effectively bounded since we never look further back than N.

- **Truncation on write.** Bot responses are truncated to a fixed
  cap before storage so big formatted reports don't bloat prompts
  later. User messages are stored as-is (Telegram caps at 4096; in
  practice they're short).

- **Caller owns the transaction.** Service flushes only — the
  worker boundary commits. Mirrors the layer contract in
  CLAUDE.md §0.1.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.conversation_context import (
    ROLE_ASSISTANT,
    ROLE_USER,
    ConversationContext,
)

logger = logging.getLogger(__name__)

# Buffer cap. 5 turns × 2 roles = 10 rows max in the prompt window.
# Larger buffers crowd the LLM context for marginal continuity wins;
# smaller ones drop the prior turn too aggressively for a 2-turn
# follow-up like "so với tháng 3 thì sao?".
DEFAULT_LIMIT = 10

# Time-to-live for context relevance. After this gap the next message
# is treated as a fresh conversation. 15 minutes matches the user's
# "feels like the same chat" intuition without keeping last-night's
# state around for tomorrow morning.
DEFAULT_TTL_MINUTES = 15

# Truncation cap for stored content. The bot's formatted output (rich
# tables, monthly reports) can be many KB; we only need a key-data
# snippet for follow-up resolution. 200 chars matches the spec and
# fits within prompt budgets for ~5-turn windows.
MAX_CONTENT_CHARS = 200


class ConversationTurn(NamedTuple):
    """One row from the buffer, in the shape callers want for prompts."""

    role: str
    content: str
    intent: str | None
    created_at: datetime


async def save_message(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    role: str,
    content: str,
    intent: str | None = None,
) -> None:
    """Append one message to the user's context buffer.

    Truncates ``content`` so big formatted bot replies don't bloat
    later prompts. Errors are logged but never raised — context is
    advisory; losing one row must not break the user-facing flow.
    """
    if not content or not content.strip():
        # Empty payloads add no signal to the prompt and just take up
        # rows + index space. Skip them.
        return
    if role not in (ROLE_USER, ROLE_ASSISTANT):
        logger.warning(
            "conversation_context.save_message: unknown role %r — skipping",
            role,
        )
        return

    truncated = _truncate(content, MAX_CONTENT_CHARS)
    try:
        db.add(
            ConversationContext(
                user_id=user_id,
                role=role,
                content=truncated,
                intent=intent,
            )
        )
        await db.flush()
    except Exception:
        # Never let a context write failure tank the actual response.
        logger.exception(
            "conversation_context.save_message failed for user %s", user_id
        )


async def get_recent_messages(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    limit: int = DEFAULT_LIMIT,
    ttl_minutes: int = DEFAULT_TTL_MINUTES,
) -> list[ConversationTurn]:
    """Return the user's last ``limit`` turns (oldest → newest).

    Filters out rows older than ``ttl_minutes`` so a long gap resets
    context. Returns an empty list on any error; callers should
    handle that as "no context" rather than failing the request.
    """
    if limit <= 0:
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=ttl_minutes)
    try:
        stmt = (
            select(ConversationContext)
            .where(
                ConversationContext.user_id == user_id,
                ConversationContext.created_at >= cutoff,
            )
            .order_by(ConversationContext.created_at.desc())
            .limit(limit)
        )
        rows = list((await db.execute(stmt)).scalars().all())
        # Caller wants chronological order for the LLM prompt; the
        # query pulls newest-first to leverage the index.
        rows.reverse()
        # Filter out anything that doesn't quack like a context row.
        # Defensive against test stubs that return arbitrary rows for
        # any SELECT — losing context on the bad path beats crashing
        # the user-facing handler.
        return [
            ConversationTurn(
                role=r.role,
                content=r.content,
                intent=r.intent,
                created_at=r.created_at,
            )
            for r in rows
            if isinstance(r, ConversationContext)
        ]
    except Exception:
        logger.exception(
            "conversation_context.get_recent_messages failed for user %s",
            user_id,
        )
        return []


def format_history_for_prompt(
    history: list[ConversationTurn],
    *,
    user_label: str = "User",
    assistant_label: str = "Bé Tiền",
) -> str:
    """Render the buffer as a plain-text block for system-prompt inclusion.

    Used by handlers that take a single string prompt (e.g. the
    advisory handler). For chat-completions / Anthropic message-list
    APIs, callers should map turns directly to ``messages`` instead —
    that path is more natural for the model.
    """
    if not history:
        return ""
    lines: list[str] = []
    for turn in history:
        label = user_label if turn.role == ROLE_USER else assistant_label
        lines.append(f"{label}: {turn.content}")
    return "\n".join(lines)


def _truncate(text: str, max_chars: int) -> str:
    """Trim long content; keep a marker so the LLM knows it was cut.

    We cut on a hard char count (not word-boundary) — context entries
    are a debug signal for the LLM, not user-facing copy, and the
    cheap truncation keeps writes O(1).
    """
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"
