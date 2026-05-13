"""Streaming primitives for long agent responses.

Telegram doesn't expose token-streaming, so we approximate it with
edit-in-place messages that grow as the agent produces text. The
``Streamer`` interface is delivery-agnostic so tests can use a
list-collecting fake, and so a future web client could implement
real SSE/WebSocket without changing the agent."""

from backend.agent.streaming.base import Streamer
from backend.agent.streaming.telegram_streamer import (
    TELEGRAM_MAX_MESSAGE_LEN,
    TelegramStreamer,
)

__all__ = ["Streamer", "TelegramStreamer", "TELEGRAM_MAX_MESSAGE_LEN"]
