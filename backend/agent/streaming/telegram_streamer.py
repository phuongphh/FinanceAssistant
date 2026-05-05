"""Stream agent output to Telegram via in-place message edits.

Telegram's API doesn't support token streaming. We approximate it:

1. ``start()`` sends a typing indicator and a "⏳ Đang phân tích..."
   placeholder. This is what makes "first chunk under 2s" achievable
   even when Claude takes 8 seconds to compose the actual response —
   the *user* sees feedback immediately, even though no real text
   has arrived yet.
2. ``send_chunk(text)`` buffers, then edits the placeholder when the
   buffer has grown enough AND enough time has passed since the last
   edit. Telegram rate-limits message edits to ~30/min per chat, so
   a min interval of 0.8 s keeps us well clear of that bound.
3. ``finish()`` performs the final flush.
4. If the cumulative text exceeds Telegram's 4096-char message
   limit, we close out the current message and start a new one for
   the overflow (split at the nearest newline boundary).

Failure modes handled inline:
- Edit failed (rate limit / message too old) → fall back to a fresh
  ``send_message`` so the user still sees output.
- Network error in the underlying httpx call → log + drop that flush
  attempt; the next send_chunk retries.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from backend.agent.streaming.base import Streamer
from backend.services import telegram_service

logger = logging.getLogger(__name__)

# Telegram's documented message-text limit. Leave headroom for
# Markdown escapes; 4000 in practice.
TELEGRAM_MAX_MESSAGE_LEN = 4000

# Tunables — chosen so a typical Tier 3 response (~600-1200 chars)
# results in 2-3 edits, not 50.
DEFAULT_MIN_CHUNK_CHARS = 80
DEFAULT_FLUSH_INTERVAL = 0.8  # seconds
PLACEHOLDER_TEXT = "⏳ Đang phân tích..."


@dataclass
class _ActiveMessage:
    """One Telegram message we're streaming into.

    We'd open more than one of these only after overflowing the
    4 KB limit; the second message starts blank and the streamer
    accumulates into it from there."""

    message_id: int
    rendered: str = ""


class TelegramStreamer(Streamer):
    def __init__(
        self,
        chat_id: int,
        *,
        parse_mode: str = "Markdown",
        min_chunk_chars: int = DEFAULT_MIN_CHUNK_CHARS,
        flush_interval: float = DEFAULT_FLUSH_INTERVAL,
        # Injection points so tests don't need to mock the entire
        # ``telegram_service`` module.
        send_message=telegram_service.send_message,
        edit_message_text=telegram_service.edit_message_text,
        send_chat_action=telegram_service.send_chat_action,
    ) -> None:
        self.chat_id = chat_id
        self.parse_mode = parse_mode
        self.min_chunk_chars = min_chunk_chars
        self.flush_interval = flush_interval
        self._send_message = send_message
        self._edit_message_text = edit_message_text
        self._send_chat_action = send_chat_action

        self._buffer = ""  # Text not yet flushed to a message edit.
        self._active: _ActiveMessage | None = None
        self._last_flush_at: float = 0.0
        self._started = False

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Send typing indicator + placeholder.

        These run sequentially because the placeholder must succeed
        for the ``message_id`` to be captured for later edits. If the
        bot token is unset, ``send_message`` returns ``None`` and we
        fall through into a degraded mode where ``send_chunk`` will
        send fresh messages instead of editing."""
        if self._started:
            return
        self._started = True

        # Typing first — fire-and-await; cheap and gives the user
        # immediate "something is happening" feedback even if
        # placeholder send is slow.
        try:
            await self._send_chat_action(self.chat_id, "typing")
        except Exception as e:  # noqa: BLE001
            logger.debug("send_chat_action failed: %s", e)

        resp = None
        try:
            resp = await self._send_message(
                self.chat_id,
                PLACEHOLDER_TEXT,
                parse_mode=self.parse_mode,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("placeholder send failed: %s", e)

        if resp and resp.get("ok") and resp.get("result"):
            mid = resp["result"].get("message_id")
            if mid:
                self._active = _ActiveMessage(message_id=mid)

    async def send_chunk(self, text: str) -> None:
        """Buffer text; flush when threshold reached."""
        if not text:
            return
        self._buffer += text
        loop = asyncio.get_event_loop()
        elapsed = loop.time() - self._last_flush_at
        if (
            len(self._buffer) >= self.min_chunk_chars
            and elapsed >= self.flush_interval
        ):
            await self._flush()

    async def finish(self) -> None:
        """Final flush of any remaining buffer."""
        if self._buffer:
            await self._flush(force=True)

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    async def _flush(self, *, force: bool = False) -> None:
        """Render whatever is buffered onto the active message.

        ``force=True`` ignores the chunk-size guard so ``finish()``
        always emits the tail. The flush_interval guard still applies
        only outside of force, because edits arrive too fast to
        Telegram's liking."""
        if not self._buffer:
            return

        # If the current active message would overflow, close it out
        # at a clean break and start a new one for the rest.
        if self._active is not None:
            available = TELEGRAM_MAX_MESSAGE_LEN - len(self._active.rendered)
            if len(self._buffer) > available:
                head, tail = _split_for_overflow(self._buffer, available)
                # Render the head into the current message.
                self._active.rendered += head
                await self._render_active()
                # Open a new message for the tail.
                self._buffer = tail
                self._active = await self._open_new_message()
                # Fall through to normal flush of tail.

        if self._active is None:
            # Degraded mode (no placeholder) — just send a new message
            # with whatever's buffered.
            await self._send_fresh_message(self._buffer)
            self._buffer = ""
            self._last_flush_at = asyncio.get_event_loop().time()
            return

        self._active.rendered += self._buffer
        self._buffer = ""
        await self._render_active()
        self._last_flush_at = asyncio.get_event_loop().time()

    async def _render_active(self) -> None:
        """Edit the current active message to the rendered text.

        On failure we fall back to a fresh message — the user still
        sees the content even if we lost the in-place update."""
        assert self._active is not None
        try:
            resp = await self._edit_message_text(
                self.chat_id,
                self._active.message_id,
                self._active.rendered or PLACEHOLDER_TEXT,
                parse_mode=self.parse_mode,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("edit_message_text raised: %s", e)
            resp = None

        if not resp:
            # The most common failure is "message is not modified" or
            # rate-limit. Fall back to a new message so the user
            # always sees something — but only when there's
            # rendered content; an empty placeholder failure is fine
            # to swallow.
            if self._active.rendered:
                await self._send_fresh_message(self._active.rendered)

    async def _send_fresh_message(self, text: str) -> None:
        try:
            await self._send_message(
                self.chat_id, text, parse_mode=self.parse_mode
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("send_message fallback raised: %s", e)

    async def _open_new_message(self) -> _ActiveMessage | None:
        """Open a fresh message for an overflow continuation."""
        try:
            resp = await self._send_message(
                self.chat_id,
                PLACEHOLDER_TEXT,
                parse_mode=self.parse_mode,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("overflow placeholder send failed: %s", e)
            return None
        if resp and resp.get("ok") and resp.get("result", {}).get("message_id"):
            return _ActiveMessage(message_id=resp["result"]["message_id"])
        return None


def _split_for_overflow(text: str, head_max: int) -> tuple[str, str]:
    """Split ``text`` so the head fits in ``head_max`` chars.

    Prefer splitting at the last newline within the bound — keeps
    paragraphs intact. Falls back to a hard split at ``head_max``
    when there's no newline (e.g. one giant code block).
    """
    if head_max <= 0:
        return "", text
    candidate = text[:head_max]
    nl = candidate.rfind("\n")
    if nl > head_max // 2:
        return text[: nl + 1], text[nl + 1 :]
    return candidate, text[head_max:]
