"""Streamer abstract interface.

Three lifecycle methods, async — that's the whole contract. The
agent never knows whether it's streaming to Telegram, a web client,
or a test list. ``send_chunk`` is allowed to be a no-op (e.g. when
buffer hasn't reached the flush threshold) and ``finish`` performs
the final flush.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class Streamer(ABC):
    """Adapter the reasoning agent calls to deliver chunks."""

    @abstractmethod
    async def start(self) -> None:
        """Set up delivery (e.g. send placeholder, typing indicator)."""

    @abstractmethod
    async def send_chunk(self, text: str) -> None:
        """Append text to the response.

        Implementations may buffer; what the user actually sees is up
        to the implementation's flush policy."""

    @abstractmethod
    async def finish(self) -> None:
        """Flush remaining buffer and clean up."""
